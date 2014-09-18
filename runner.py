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
import subprocess
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
    return {"root": project_dir, "dim_names": dims, "cases": cases}

class TestProjectScanner:
    def __init__(self, project_dir):
        self.project_dir = project_dir
    def scan(self):
        return parse_project_config(self.project_dir)

# Data structure
#
# Test Project: The following dictionary:
# {"root": "PATH", "dim_names": [n1, n2], "cases": test_cases}
# Test cases can be recursively organized or flat, the following is the flat case:
# Test Case: The following dictionary
# ```python
# {
#      "project_root": "PATH"                     # Absolute path for the project root
#      "vpath": OrderedDict([(k1, v1), (k2, v2)]) # Virtual path for the case
#      "sepc": {
#          "cmd": ["exe", "args"]   # Command list to run the case
#          "envs": {k1: v1, k2: v2} # Environment variables
#          "run": {
#              "nprocs": 4,      # Number for procs for the case
#              "nnodes": 1,      # Number of nodes for the case
#              "procs_per_node": # Number of process per node
#              "tasks_per_proc": # Number of tasks per process
#          }
#          "results": ["fn1", "fn2"] # Files containing results
#      }
# }
#
class TestCaseFilter:
    '''TestCaseFilter - Filter test cases using path-like strings'''
    def __init__(self, filter_spec):
        assert isinstance(filter_spec, str) or isinstance(filter_spec, unicode)
        compiled_filter = []
        ptn = re.compile(r"\{(.*?)\}")
        for seg in filter_spec.split("/"):
            m = ptn.match(seg)
            if m:
                s = [s.strip() for s in m.group(1).split(",")]
            else:
                s = [seg]
            compiled_filter.append(s)
        self.compiled_filter = compiled_filter

    def match(self, vpath):
        def seg_match(seg, compiled_spec):
            for ptn in compiled_spec:
                if fnmatch.fnmatch(seg, ptn):
                    return True
            return False
        for i, seg in enumerate(vpath.values()):
            if not seg_match(seg, self.compiled_filter[i]):
                return False
        return True

    def filter(self, flat_cases, exclude=False):
        result = []
        for case in flat_cases:
            match = self.match(case["vpath"])
            choose = not match if exclude else match
            if choose:
                result.append(case)
        return result


class TestProjectUtility:
    def __init__(self):
        pass

    def flatten(self, project_info):
        root = project_info["root"]
        dim_names = project_info["dim_names"]
        cases = []
        def recursive_flatten(node, vpath):
            if len(vpath) == len(dim_names):
                case = {"project_root": root, "vpath": vpath, "spec": node}
                cases.append(case)
                return
            for k, v in node.iteritems():
                new_vpath = OrderedDict(vpath)
                new_vpath[dim_names[len(vpath)]] = k
                recursive_flatten(v, new_vpath)
        recursive_flatten(project_info["cases"], OrderedDict())
        return {"root": root, "dim_names": dim_names, "cases": cases}

    def gather_dim_values(self, project_info):
        dim_names = project_info["dim_names"]
        values = [set() for i in dim_names]
        gathered_values = OrderedDict(zip(dim_names, values))
        def recursive_gather(node, level):
            if level == len(dim_names): # this is the leaf level
                return
            for k, v in node.iteritems():
                gathered_values[dim_names[level]].add(k)
                recursive_gather(v, level + 1)
        recursive_gather(project_info["cases"], 0)
        return gathered_values


class TestCaseRunner:
    def __init__(self, runner, timeout=None, progress=None):
        self.runner = runner
        self.timeout = timeout
        self.progress = progress
        if runner == "mpirun":
            def make_cmd(case, timeout):
                exec_cmd = map(str, case["cmd"])
                nprocs = str(case["run"]["nprocs"])
                timeout_cmd = []
                if timeout:
                    timeout_cmd = ["/usr/bin/timeout", "{0}m".format(timeout)]
                mpirun_cmd = ["mpirun", "-np", nprocs]
                return timeout_cmd + mpirun_cmd + exec_cmd
            def check_ret(ret_code):
                if ret_code == 0:
                    return 0  # success
                elif ret_code == 124:
                    return 1  # timeout
                else:
                    return -1 # application terminated error
            self.make_cmd = make_cmd
            self.check_ret = check_ret
        elif runner_name == "yhrun":
            def make_cmd(case, timeout):
                exec_cmd = map(str, case["cmd"])
                run = case["run"]
                nprocs = str(run["nprocs"])
                nnodes = run["nnodes"] if "nnodes" in run else None
                tasks_per_proc = run.value("tasks_per_proc", None)
                yhrun_cmd = ["yhrun"]
                if nnodes:
                    yhrun_cmd.extend(["-N", nnodes])
                yhrun_cmd.extend(["-n", nprocs])
                if tasks_per_proc:
                    yhrun_cmd.extend(["-c", tasks_per_proc])
                if timeout:
                    yhrun_cmd.extend(["-t", str(timeout)])
                yhrun_cmd.extend(["-p", "Super_zh"])
                return yhrun_cmd + exec_cmd
            def check_ret(ret_code):
                if ret_code == 0:
                    return "success"
                elif ret_code == 124:
                    return "timeout"
                else:
                    return "failed"
            self.make_cmd = make_cmd
            self.check_ret = check_ret
        else:
            raise RuntimeError("Unsupport runner: " + runner)

    def run(self, case_spec):
        root = case_spec["project_root"]
        vpath = case_spec["vpath"]
        cfg = case_spec["spec"]
        work_dir = os.path.join(root, *vpath.values())
        if not os.path.exists(work_dir):
            os.makedirs(work_dir)
        env = dict(os.environ)
        for k, v in cfg["envs"].iteritems():
            env[k] = str(v)
        out_fn = os.path.join(work_dir, "STDOUT")
        err_fn = os.path.join(work_dir, "STDERR")
        cmd = self.make_cmd(cfg, self.timeout)
        if self.progress:
            self.progress.begin_case(case_spec)
        ret = subprocess.call(cmd, env=env, cwd=work_dir,
                              stdout=file(out_fn, "w"), stderr=file(err_fn, "w"))
        stat = self.check_ret(ret)
        if self.progress:
            self.progress.end_case(case_spec, stat)
        return stat

    def run_batch(self, cases):
        '''Run a collection of test cases'''
        finished_cases = []
        timeout_cases = []
        failed_cases = []
        for case in cases:
            status = self.run(case)
            if status == 0:
                finished_cases.append(case)
            elif status == 1:
                timeout_cases.append(case)
                failed_cases.append(case)
            else:
                failed_cases.append(case)
        return {"finished": finished_cases,
                "failed": failed_cases,
                "timeout": timeout_cases}

def main():
    parser = argparse.ArgumentParser(description=__doc__)

    ag = parser.add_argument_group("Global options")
    ag.add_argument("project_dir", metavar="PROJECT_DIR",
                    help="Directory of the test project")
    ag.add_argument("--result-dir",
                    help="Directory for test results")

    ag = parser.add_argument_group("Filter options")
    ag.add_argument("--exclude",
                    help="Test cases to exclude, support wildcards")
    ag.add_argument("--include",
                    help="Test cases to include, support wildcards")

    ag = parser.add_argument_group("Case runner options")
    ag.add_argument("--case-runner",
                    help="Runner to choose, can be mpirun and yhrun")
    ag.add_argument("--timeout",
                    help="Timeout for each case, in minites")

    config = parser.parse_args()

    proj = TestProjectScanner(config.project_dir).scan()
    util = TestProjectUtility()
    flat_proj = util.flatten(proj)
    dim_values = util.gather_dim_values(proj)
    print "Test project information: "
    print "  project root: {0}".format(flat_proj["root"])
    print "  dimensions: {0}".format("/".join(flat_proj["dim_names"]))
    for k, v in dim_values.iteritems():
        print "    {0}: {1}".format(k, ", ".join(v))
    print "  total cases: {0}".format(len(flat_proj["cases"]))
    exec_part = flat_proj["cases"]
    if config.exclude:
        exec_part = TestCaseFilter(config.exclude).filter(exec_part, True)
        print "  exclude pattern: {0}".format(config.exclude)
    elif config.include:
        exec_part = TestCaseFilter(config.include).filter(exec_part, False)
        print "  include pattern: {0}".format(config.include)
    print "  cases in the run: {0}".format(len(exec_part))
    class MyProgress:
        def begin_case(self, case_spec):
            print "  Run {0} ...".format("/".join(case_spec["vpath"].values())),
        def end_case(self, case_spec, stat):
            if stat == 0:
                s = "Done."
            elif stat == 1:
                s = "Timeout."
            else:
                s = "Failed."
            print s
    runner = TestCaseRunner("mpirun", progress=MyProgress())
    print "Run progress:"
    stats = runner.run_batch(exec_part)
    print "Run finished. {0} cases in total, of which".format(len(exec_part))
    print "  {0} finished, {1} failed".format(len(stats["finished"]), len(stats["failed"]))
    print "  {0} failed due to timeout".format(len(stats["timeout"]))

if __name__ == "__main__":
    main()
