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
import string
import subprocess
import pprint
from collections import OrderedDict


class TestProjectScanner:
    '''TestProjectScanner - Scan a test project for test cases'''
    def __init__(self, project_root):
        '''Create a scanner object for project at 'project_dir' '''
        self.project_root = os.path.abspath(project_root)
        conf_fn = os.path.join(self.project_root, "TestConfig.json")
        if not os.path.exists(conf_fn):
            raise RuntimeError("Invalid project directory: %s" % project_root)
        conf = json.load(file(conf_fn))
        assert "project" in conf
        project_info = conf["project"]
        self.dim_names = project_info["dimensions"]

    def scan(self):
        '''Scan the project directory and return a list of test cases

        Return: A dict containing the following fields:
            {'root': string, 'dim_names': list, 'cases': list}

        Each case in 'cases' is the following dict:
            {'project_root': string, 'vpath': OrderedDict, 'spec': dict}
        '''
        test_cases = []

        def do_scan(vpath, level):
            curr_dir = os.path.join(self.project_root, *vpath.values())
            conf_fn = os.path.join(curr_dir, "TestConfig.json")
            assert os.path.exists(conf_fn)
            conf = json.load(file(conf_fn))
            if level == len(self.dim_names):
                assert "test_case" in conf
                case = {"spec": conf["test_case"], "vpath": vpath,
                        "project_root": self.project_root}
                test_cases.append(case)
            else:
                assert "sub_directories" in conf
                dirs = conf["sub_directories"]
                dir_list = []
                if isinstance(dirs, list):
                    dir_list = dirs
                elif isinstance(dirs, dict):
                    assert "directories" in dirs
                    dir_list = dirs["directories"]
                else:
                    raise RuntimeError("Invalid sub_directory spec")
                for path in dir_list:
                    new_vpath = OrderedDict(vpath)
                    new_vpath[self.dim_names[level]] = path
                    do_scan(new_vpath, level+1)

        do_scan(OrderedDict(), 0)
        return {"root": self.project_root, "dim_names": self.dim_names,
                "cases": test_cases}


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

    def gather_dim_values(self, project_info):
        dim_names = project_info["dim_names"]
        values = [set() for i in dim_names]
        gathered_values = OrderedDict(zip(dim_names, values))
        for case in project_info["cases"]:
            vpath = case['vpath']
            for k, v in vpath.iteritems():
                gathered_values[k].add(v)
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
                    return -1  # application terminated error
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
                              stdout=file(out_fn, "w"),
                              stderr=file(err_fn, "w"))
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

    proj = TestProjectScanner(config.project_dir)
    util = TestProjectUtility()
    flat_proj = proj.scan()
    dim_values = util.gather_dim_values(flat_proj)
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
    print "  {0} finished, {1} failed".format(len(stats["finished"]),
                                              len(stats["failed"]))
    print "  {0} failed due to timeout".format(len(stats["timeout"]))

if __name__ == "__main__":
    main()
