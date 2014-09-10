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
    func_name = cfg["func"]
    func_args = cfg["args"] if "args" in cfg else {}
    if not os.path.isabs(python_fn):
        cwd = os.path.join(project_root, *cfg_vpath.values())
        python_fn = os.path.abspath(os.path.join(cwd, python_fn))
    python_result = {}
    execfile(python_fn, python_result)
    func = python_result[func_name]
    vp = OrderedDict(cfg_vpath.items() + case_vpath.items())
    vp["project_root"] = project_root
    result = func(vp, **func_args)
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
    dims = []
    for n in cfg["dimensions"]["names"]:
        dims.append(cfg["dimensions"]["values"][n])
    result = {}
    for k in itertools.product(*dims):
        case_vpath = OrderedDict(zip(cfg["dimensions"]["names"], k))
        test_case = make_case(project_root, vpath, case_vpath, cfg)
        dict_assign(result, k, test_case)
    return result

def recursively_parse_config(project_root, dim_names, vpath, current_dir):
    fn = os.path.join(current_dir, "TestConfig.json")
    cnt = parse_json(fn)
    result = None
    if "sub_directories" in cnt:
        # For subdirectories, we support two grammars:
        # 1. simple list: [dir0, dir1, dir2, ...]
        # 2. descriptive dict:
        #    {"dimension": dim, "directories": [dir0, ...]}
        #result = OrderedDict()
        result = {}
        if isinstance(cnt["sub_directories"], list):
            dir_list = cnt["sub_directories"]
        elif isinstance(cnt["sub_directories"], dict):
            dir_list = cnt["sub_directories"]["directories"]
        else:
            raise RuntimeError("Invalid subdirectory spec.")
        for sub_dir in dir_list:
            p = os.path.join(current_dir, sub_dir)
            new_vpath = OrderedDict(vpath)
            vpath_key = dim_names[len(vpath)]
            new_vpath[vpath_key] = sub_dir
            result[sub_dir] = recursively_parse_config(project_root, dim_names, new_vpath, p)
    elif "test_matrix" in cnt:
        # For test_matrix, it has the following format:
        #     {"dimensions": {names, values}, "test_case_generator": gen,
        #      generator_ralated_config}
        result = generate_test_matrix(project_root, vpath, cnt["test_matrix"])
    elif "test_case" in cnt:
        result = cnt["test_case"]
    else:
        raise RuntimeError("Unsupported config type")
    return result


def parse_project_config(project_dir):
    fn = os.path.join(project_dir, "TestConfig.json")
    cnt = parse_json(fn)
    project_info = cnt["project"]
    dims = project_info["dimensions"]
    pos = OrderedDict()
    test_config = recursively_parse_config(project_dir, dims, pos, project_dir)
    return test_config

def main():
    parser = argparse.ArgumentParser(description=__doc__)

    ag = parser.add_argument_group("Global options")
    ag.add_argument("project_dir", metavar="PROJECT_DIR",
                    help="Directory of the test project")
    ag.add_argument("--result-dir",
                    help="Directory for test results")

    ag = parser.add_argument_group("Filter options")
    ag.add_argument("--except",
                    help="Test cases to exclude, support wildcards")
    ag.add_argument("--only",
                    help="Test cases to include, support wildcards")

    ag = parser.add_argument_group("Case runner options")
    ag.add_argument("--case-runner",
                    help="Runner to choose, can be mpirun and yhrun")
    ag.add_argument("--timeout",
                    help="Timeout for each case, in minites")

    config = parser.parse_args()

    cfg = parse_project_config(config.project_dir)
    pprint.pprint(cfg)

if __name__ == "__main__":
    main()
