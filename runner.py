#!/usr/bin/env python2.7
#

''' Runner - Versatile testcase runner

Runner run a hierarchy of test cases and store the results in another hierarchy.
It provides options such as test case filter, timeout etc, to make repeated test
easy.
'''

import os
import sys
import argparse
import re
import fnmatch
import json
import itertools
import string
import pprint
from collections import OrderedDict

def ununicodify(obj):
    '''Turn every unicode instance in an object into str

    Python 2 deserializes json strings into unicode objects, which is different
    than str. This makes indexing and comparing these object hard. This function
    call str on every unicode instance of obj and keeps other parts untouched,
    returns a new object without any unicode instances.
    '''
    result = None
    if isinstance(obj, dict):
        result = dict()
        for k, v in obj.iteritems():
            k1 = str(k) if isinstance(k, unicode) else k
            result[k1] = ununicodify(v)
    elif isinstance(obj, list):
        result = []
        for v in obj:
            result.append(ununicodify(v))
    elif isinstance(obj, unicode):
        result = str(obj)
    else:
        result = obj
    return result

def parse_json(fn):
    return ununicodify(json.load(file(fn)))

def dict_assign(dict_like, keys, val):
    assert isinstance(dict_like, dict)
    r = dict_like
    for k in keys[:-1]:
        if k not in r:
            r[k] = {}
        r = r[k]
    r[keys[-1]] = val

def substitute_nested_template(template, subs):
    result = None
    if isinstance(template, dict):
        result = {}
        for k, v in template.iteritems():
            result[k] = substitute_nested_template(v, subs)
    elif isinstance(template, list):
        result = []
        for v in template:
            result.append(substitute_nested_template(v, subs))
    elif isinstance(template, str) or isinstance(template, unicode):
        t = string.Template(template)
        result = t.safe_substitute(subs)
        if re.match(r"^[\d\s+\-*/()]+$", result):
            result = eval(result)
    else:
        result = template
    return result

def make_case_template(project_root, cfg_vpath, case_vpath, template):
    subs = dict(cfg_vpath.items() + case_vpath.items())
    subs["project_root"] = project_root
    return substitute_nested_template(template, subs)

def make_case_custom(project_root, cfg_vpath, case_vpath, cfg):
    python_fn = cfg["import"]
    assert isinstance(python_fn, str) or isinstance(python_fn, unicode)
    # substitute template variables since we support it.
    variables = dict(cfg_vpath.items() + case_vpath.items())
    variables["project_root"] = project_root
    python_fn = string.Template(python_fn).safe_substitute(variables)
    if not os.path.isabs(python_fn):
        cwd = os.path.join(project_root, *cfg_vpath.values())
        python_fn = os.path.abspath(os.path.join(cwd, python_fn))
    python_result = {}
    execfile(python_fn, python_result)
    func_name = cfg["func"]
    func_args = cfg["args"] if "args" in cfg else {}
    func = python_result[func_name]
    result = func(project_root, cfg_vpath, case_vpath, **func_args)
    return result

def make_case(project_root, cfg_vpath, case_vpath, config):
    generator_type = config["test_case_generator"]
    if generator_type == "template":
        template = config["template"]
        return make_case_template(project_root, cfg_vpath, case_vpath, template)
    elif generator_type == "custom":
        custom_cfg = config["custom_generator"]
        return make_case_custom(project_root, cfg_vpath, case_vpath, custom_cfg)
    else:
        raise RuntimeError("Unknown generator type: {0}".format(generator_type))

def generate_test_matrix(project_root, vpath, cfg):
    dim_values = []
    for n in cfg["dimensions"]["names"]:
        dim_values.append(cfg["dimensions"]["values"][n])
    result = {}
    for k in itertools.product(*dim_values):
        case_vpath = OrderedDict(zip(cfg["dimensions"]["names"], k))
        test_case = make_case(project_root, vpath, case_vpath, cfg)
        dict_assign(result, map(str, k), test_case)
    return result


def recursively_parse_config(project_root, dim_names, vpath, current_dir):
    fn = os.path.join(current_dir, "TestConfig.json")
    cfg = parse_json(fn)
    result = None
    if "sub_directories" in cfg:
        # For subdirectories, we support two grammars:
        # 1. simple list: [dir0, dir1, dir2, ...]
        # 2. descriptive dict:
        #    {"dimension": dim, "directories": [dir0, ...]}
        #result = OrderedDict()
        if isinstance(cfg["sub_directories"], list):
            dir_list = cfg["sub_directories"]
        elif isinstance(cfg["sub_directories"], dict):
            dir_list = cfg["sub_directories"]["directories"]
        else:
            errmsg = "Invalid sub_directories spec in '{0}'".format(fn)
            raise RuntimeError(errmsg)
        result = dict() # TODO(zyang): change to OrderedDict when mature
        for sub_dir in dir_list:
            p = os.path.join(current_dir, sub_dir)
            new_vpath = OrderedDict(vpath)
            vpath_key = dim_names[len(vpath)]
            new_vpath[vpath_key] = sub_dir
            r = recursively_parse_config(project_root, dim_names, new_vpath, p)
            result[sub_dir] = r
    elif "test_matrix" in cfg:
        # For test_matrix, it has the following format:
        #     {"dimensions": {names, values}, "test_case_generator": gen,
        #      generator_ralated_config}
        result = generate_test_matrix(project_root, vpath, cfg["test_matrix"])
    elif "test_case" in cfg:
        # For single test case, it can use predefined template variables:
        # project_root and all avaliable vpath values.
        subs = dict(vpath)
        subs["project_root"] = project_root
        result = substitute_nested_template(cfg["test_case"], subs)
    else:
        # Other type is not supported.
        errmsg = "Invalid TestConfig file: '{0}'".format(fn)
        raise RuntimeError(errmsg)
    return result


def parse_project_config(project_dir):
    project_dir = os.path.abspath(project_dir)
    fn = os.path.join(project_dir, "TestConfig.json")
    cfg = parse_json(fn)
    project_info = cfg["project"]
    dims = project_info["dimensions"]
    vpath = OrderedDict()
    cases = recursively_parse_config(project_dir, dims, vpath, project_dir)
    return {"dim_names": dims, "cases": cases}

def parse_filter_spec(spec):
    assert isinstance(spec, str) or isinstance(spec, unicode)
    segs = spec.split("/")
    def parse_seg(seg):
        # Supported grammar: {ID1, ID2, ID3, ...} or ID, where ID can be any
        # unix wildcards as specified in fnmatch module
        ptn = re.compile("\{(.*?)\}")
        m = ptn.match(seg)
        if m:
            s = [s.strip() for s in m.group(1).split(",")]
        else:
            s = [seg]
        return s
    return [parse_seg(seg) for seg in segs]

def vpath_match(vpath, spec):
    def match_in_ptn(dim_value, ptn):
        for p in ptn:
            if fnmatch.fnmatch(dim_value, p):
                return True
        return False
    for i, seg in enumerate(vpath.values()):
        if not match_in_ptn(seg, spec[i]):
            return False
    return True

def flattern_cases(cases, dim_names, vpath, result):
    if len(vpath) == len(dim_names):
        case = {"vpath": vpath, "spec": cases}
        result.append(case)
        return
    for k, v in cases.iteritems():
        new_vpath = OrderedDict(vpath)
        new_vpath[dim_names[len(vpath)]] = k
        flattern_cases(v, dim_names, new_vpath, result)

def filter_cases(proj, filter_spec, exclude):
    parsed_spec = parse_filter_spec(filter_spec)
    flat_cases = []
    flattern_cases(proj["cases"], proj["dim_names"], OrderedDict(), flat_cases)
    result = []
    for case in flat_cases:
        match = vpath_match(case["vpath"], parsed_spec)
        choose = not match if exclude else match
        if choose:
            result.append(case)
    return result

def run_cases(cases):
    print cases

    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    ag = parser.add_argument_group("Global options")
    ag.add_argument("project_dir", metavar="PROJECT_DIR",
                    help="Directory of the test project")
    ag.add_argument("--result-dir",
                    help="Directory for test results")

    ag = parser.add_argument_group("Filter options")
    ag.add_argument("--except1",
                    help="Test cases to exclude, support wildcards")
    ag.add_argument("--only",
                    help="Test cases to include, support wildcards")

    ag = parser.add_argument_group("Case runner options")
    ag.add_argument("--case-runner",
                    help="Runner to choose, can be mpirun and yhrun")
    ag.add_argument("--timeout",
                    help="Timeout for each case, in minites")

    config = parser.parse_args()

    proj = parse_project_config(config.project_dir)
    if config.except1:
        new_cases = filter_cases(proj, config.except1, True)
    elif config.only:
        new_cases = filter_cases(proj, config.only, False)
    else:
        new_cases = []
        flattern_cases(proj["cases"], proj["dim_names"],
                       OrderedDict(), new_cases)
    pprint.pprint(new_cases)
    # run_cases(new_cases)

if __name__ == "__main__":
    main()
