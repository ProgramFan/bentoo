#!/usr/bin/env python2.7
# coding: utf-8
''' Runner - Versatile testcase runner

Runner run a hierarchy of test cases and store the results in another
hierarchy.  It provides options such as test case filter, timeout etc, to make
repeated test easy.
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


class TestProjectReader:

    '''Scan a test project for test cases'''

    def __init__(self, project_root):
        '''Create a scanner object for project at 'project_dir' '''
        self.project_root = os.path.abspath(project_root)
        conf_fn = os.path.join(self.project_root, "TestProject.json")
        if not os.path.exists(conf_fn):
            raise RuntimeError("Invalid project directory: %s" % project_root)
        conf = json.load(file(conf_fn))
        self.name = conf["name"]
        self.test_factors = conf["test_factors"]
        self.data_files = conf["data_files"]
        test_cases = conf["test_cases"]
        self.test_cases = zip(test_cases["test_vectors"],
                              test_cases["case_paths"])

    def check(self):
        '''Check project's validity

        Check project's validity by checking the existance of each case's
        working directories and specification file. Specification content may
        be checked in the future.

        Exceptions:
            RuntimeError: Any error found in the check

            This shall be refined in the future.

        '''
        for k, v in self.test_cases.iteritems():
            case_fullpath = os.path.join(self.project_root, v)
            if not os.path.exists(case_fullpath):
                raise RuntimeError(
                    "Test case '%s' not found in '%s'" %
                    (k, case_fullpath))
            case_spec_fullpath = os.path.join(case_fullpath, "TestCase.json")
            if not os.path.exists(case_spec_fullpath):
                raise RuntimeError(
                    "Test case spec for '%s' is not found in '%s'" %
                    (k, case_fullpath))
            # TODO: check the content of case spec (better with json-schema)

    def itercases(self):
        for test_vector, case_path in self.test_cases:
            case_spec_fullpath = os.path.join(
                self.project_root,
                case_path,
                "TestCase.json")
            case_spec = json.load(file(case_spec_fullpath))
            yield {
                "case_path": os.path.join(self.project_root, case_path),
                "run_spec": case_spec,
                "test_vector": test_vector
            }


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
        test_vector = case_spec["test_vector"]
        case_path = case_spec["case_path"]
        run_spec = case_spec["run_spec"]
        assert os.path.isabs(case_path)
        env = dict(os.environ)
        for k, v in run_spec["envs"].iteritems():
            env[k] = str(v)
        out_fn = os.path.join(case_path, "STDOUT")
        err_fn = os.path.join(case_path, "STDERR")
        cmd = self.make_cmd(run_spec, self.timeout)
        if self.progress:
            self.progress.begin_case(case_spec)
        ret = subprocess.call(cmd,
                              env=env,
                              cwd=case_path,
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
        return {
            "finished": finished_cases,
            "failed": failed_cases,
            "timeout": timeout_cases
        }


class SimpleProgress:

    def begin_case(self, case_spec):
        pretty_path = os.path.relpath(case_spec["case_path"])
        print "  Run {0} ...".format(pretty_path),

    def end_case(self, case_spec, stat):
        if stat == 0:
            s = "Done."
        elif stat == 1:
            s = "Timeout."
        else:
            s = "Failed."
        print s


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    ag = parser.add_argument_group("Global options")
    ag.add_argument("project_root",
                    help="Root directory of the test project")

    ag = parser.add_argument_group("Filter options")
    ag.add_argument("--exclude",
                    help="Test cases to exclude, support wildcards")
    ag.add_argument("--include",
                    help="Test cases to include, support wildcards")

    ag = parser.add_argument_group("Case runner options")
    ag.add_argument("--case-runner",
                    choices=["mpirun", "yhrun"],
                    default="mpirun",
                    help="Runner to choose, default to mpirun")
    ag.add_argument("--timeout",
                    default=5,
                    help="Timeout for each case, in minites")

    config = parser.parse_args()

    proj = TestProjectReader(config.project_root)
    print "Test project information: "
    print "  project root: {0}".format(proj.project_root)
    print "  test factors: {0}".format(", ".join(proj.test_factors))

    runner = TestCaseRunner("mpirun", progress=SimpleProgress())
    print "Run progress:"
    stats = runner.run_batch(proj.itercases())
    print "Run finished."
    print "  {0} finished, {1} failed".format(len(stats["finished"]),
                                              len(stats["failed"]))
    print "  {0} failed due to timeout".format(len(stats["timeout"]))


if __name__ == "__main__":
    main()
