#!/usr/bin/env python2.7
#

import sys
import os
import argparse
import string
import re
import json
import shutil
import glob
from collections import OrderedDict


def parse_json(fn):
    '''Parse a json file and return python objects

    Difference from builtin json module:
    1. Accepts file name instead of file object
    2. Support "//" like comments in json file
    3. Objects does not contains unicode objects.
    '''

    def ununicodify(obj):
        '''Turn every unicode instance in an json object into str'''
        result = None
        if isinstance(obj, OrderedDict):
            result = OrderedDict()
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
    content = file(fn).read()
    content = re.sub(r"\s+//.*$", "", content)
    return ununicodify(json.loads(content, object_pairs_hook=OrderedDict))


def substitute_and_evaluate(template, subs):
    result = None
    if isinstance(template, dict):
        result = {}
        for k, v in template.iteritems():
            result[k] = substitute_and_evaluate(v, subs)
    elif isinstance(template, list):
        result = []
        for v in template:
            result.append(substitute_and_evaluate(v, subs))
    elif isinstance(template, str) or isinstance(template, unicode):
        t = string.Template(template)
        result = t.safe_substitute(subs)
        if re.match(r"^[\d\s+\-*/()]+$", result):
            result = eval(result)
    else:
        result = template
    return result


def make_case(conf_root, dest_root, cfg_vpath, case_vpath, cfg):
    generator_type = cfg["test_case_generator"]
    if generator_type == "template":
        template = cfg["template"]
        subs = dict(cfg_vpath.items() + case_vpath.items())
        p = os.path.join(conf_root, *cfg_vpath.values())
        p = os.path.join(p, *case_vpath.values())
        project_root = os.path.relpath(conf_root, p)
        subs["project_root"] = project_root
        return substitute_and_evaluate(template, subs)
    elif generator_type == "custom":
        custom_cfg = cfg["custom_generator"]
        python_fn = custom_cfg["import"]
        assert isinstance(python_fn, str) or isinstance(python_fn, unicode)
        # substitute template variables since we support it.
        variables = dict(cfg_vpath.items() + case_vpath.items())
        variables["project_root"] = conf_root
        python_fn = string.Template(python_fn).safe_substitute(variables)
        if not os.path.isabs(python_fn):
            cwd = os.path.join(conf_root, *cfg_vpath.values())
            python_fn = os.path.abspath(os.path.join(cwd, python_fn))
        python_result = {}
        execfile(python_fn, python_result)
        func_name = custom_cfg["func"]
        func_args = custom_cfg["args"] if "args" in custom_cfg else {}
        func = python_result[func_name]
        result = func(conf_root, dest_root, cfg_vpath, case_vpath, **func_args)
        return result
    else:
        raise RuntimeError("Unknown generator type: {0}".format(generator_type))


def make_test_matrix(conf_root, dest_root, cfg_vpath, cfg):
    dim_names = cfg["dimensions"]["names"]
    dim_values = []
    for n in dim_names:
        dim_values.append(map(str, cfg["dimensions"]["values"][n]))
    assert dim_values is not None

    def do_generate(case_vpath, level):
        dest_dir = os.path.join(dest_root, *cfg_vpath.values())
        dest_dir = os.path.join(dest_dir, *case_vpath.values())
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
        if level == len(dim_names):
            case = make_case(conf_root, dest_root, cfg_vpath, case_vpath, cfg)
            dest_fn = os.path.join(dest_dir, "TestConfig.json")
            conf = {"test_case": case}
            json.dump(conf, file(dest_fn, "w"), indent=4)
        else:
            conf = {"sub_directories": dim_values[level]}
            for new_dir in dim_values[level]:
                new_vpath = OrderedDict(case_vpath)
                new_vpath[dim_names[level]] = new_dir
                do_generate(new_vpath, level + 1)
            dest_fn = os.path.join(dest_dir, "TestConfig.json")
            json.dump(conf, file(dest_fn, "w"), indent=4)

    do_generate(OrderedDict(), 0)
    return dim_values[0]


class TestProjectGenerator:
    '''TestProjectGenerator - Create standard test project from specification'''
    def __init__(self, conf_dir, link_files=False, force_overwrite=False):
        self.conf_path = os.path.abspath(conf_dir)
        self.link_files = link_files
        self.force_overwrite = force_overwrite
        conf_fn = os.path.join(self.conf_path, "TestConfig.json")
        assert os.path.exists(conf_fn)
        conf = parse_json(conf_fn)
        assert "project" in conf
        self.dim_names = conf["project"]["dimensions"]

    def save(self, dest_dir):
        self.dest_path = os.path.abspath(dest_dir)
        if self.dest_path == self.conf_path:
            raise RuntimeError("Dest path can not be conf path")
        self._do_write(OrderedDict())

    def _do_write(self, vpath):
        # Read "TestConfig.json"
        curr_dir = os.path.join(self.conf_path, *vpath.values())
        conf_fn = os.path.join(curr_dir, "TestConfig.json")
        assert os.path.exists(conf_fn)
        conf = parse_json(conf_fn)
        # Special case for top level directory: also save project information
        new_conf = {}
        if "project" in conf:
            new_conf["project"] = conf["project"]
        # Make dest directory
        dest_dir = os.path.join(self.dest_path, *vpath.values())
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
        # Handle "data_files" specification
        if "data_files" in conf:
            file_lists = []
            # TODO: support shell-like wildcards
            for n in conf["data_files"]:
                file_lists.append(n)
            for path in file_lists:
                src = os.path.join(curr_dir, path)
                dst = os.path.join(dest_dir, path)
                # TODO: support link file and force write option
                if os.path.isfile(src):
                    shutil.copyfile(src, dst)
                elif os.path.isdir(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    raise ValueError("Unsupported file: %s" % src)
            new_conf["data_files"] = file_lists
        # Handle test suite specification: currently only support 'test_case',
        # 'test_matrix' and 'sub_directories'.
        if "sub_directories" in conf:
            # For subdirectories, we iterate over each directory and recursively
            # handle their content.
            spec = conf["sub_directories"]
            if isinstance(spec, list):
                dir_list = spec
            elif isinstance(spec, dict):
                assert "directories" in spec
                assert "dimension_name" in spec
                dir_list = spec["directories"]
            else:
                errmsg = "Invalid sub_directories spec: '{0}'".format(spec)
                raise RuntimeError(errmsg)
            dim_name = self.dim_names[len(vpath)]
            for path in dir_list:
                new_vpath = OrderedDict(vpath)
                new_vpath[dim_name] = path
                self._do_write(new_vpath)
            new_conf["sub_directories"] = dir_list
        elif "test_matrix" in conf:
            # For test matrix, we generate test cases in dest_path, and also
            # reconstruct directory hierarchy there.
            spec = conf["test_matrix"]
            d = make_test_matrix(self.conf_path, self.dest_path, vpath, spec)
            new_conf["sub_directories"] = d
        elif "test_case" in conf:
            spec = conf["test_case"]
            subs = dict(vpath)
            p = os.path.join(self.conf_path, *vpath.values())
            project_root = os.path.relpath(self.conf_path, p)
            subs["project_root"] = project_root
            result = substitute_and_evaluate(spec, subs)
            new_conf["test_case"] = result
        else:
            # Other type is not supported.
            errmsg = "Invalid TestConfig file: '{0}'".format(conf_fn)
            raise RuntimeError(errmsg)
        dest_fn = os.path.join(dest_dir, "TestConfig.json")
        json.dump(new_conf, file(dest_fn, "w"), indent=4)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("spec_dir", help="Project specification directory")
    parser.add_argument("run_dir", help="Project run directory")

    ag = parser.add_argument_group("Generator Options")
    ag.add_argument("--use-absolute-path",
                    default=False, action="store_true",
                    help="Use absolute path for file paths")
    ag.add_argument("--link-files",
                    default=False, action="store_true",
                    help="Link data files instead of copy them")

    config = parser.parse_args()
    generator = TestProjectGenerator(config.spec_dir)
    generator.save(config.run_dir)


if __name__ == "__main__":
    main()
