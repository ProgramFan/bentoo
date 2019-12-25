# coding: utf-8
#

import os
import json

class TestProjectReader(object):
    '''Scan a test project for test cases'''
    def __init__(self, project_root):
        '''Create a scanner object for project at 'project_dir' '''
        self.project_root = os.path.abspath(project_root)
        conf_fn = os.path.join(self.project_root, "TestProject.json")
        if not os.path.exists(conf_fn):
            raise RuntimeError("Invalid project directory: %s" % project_root)
        conf = json.load(open(conf_fn))
        version = conf.get("version", 1)
        if version != 1:
            raise RuntimeError("Unsupported project version '%s': Only 1 " %
                               version)
        self.name = conf["name"]
        self.test_factors = conf["test_factors"]
        self.test_cases = conf["test_cases"]
        self.data_files = conf.get("data_files", [])

        self.last_stats = None
        stats_fn = os.path.join(self.project_root, "run_stats.json")
        if os.path.exists(stats_fn):
            self.last_stats = json.load(open(stats_fn))

    def check(self):
        '''Check project's validity

        Check project's validity by checking the existance of each case's
        working directories and specification file. Specification content may
        be checked in the future.

        Exceptions:
            RuntimeError: Any error found in the check

            This shall be refined in the future.

        '''
        for k, v in self.test_cases.items():
            case_fullpath = os.path.join(self.project_root, v)
            if not os.path.exists(case_fullpath):
                raise RuntimeError("Test case '%s' not found in '%s'" %
                                   (k, case_fullpath))
            case_spec_fullpath = os.path.join(case_fullpath, "TestCase.json")
            if not os.path.exists(case_spec_fullpath):
                raise RuntimeError(
                    "Test case spec for '%s' is not found in '%s'" %
                    (k, case_fullpath))
            # TODO: check the content of case spec (better with json-schema)

    def itercases(self):
        '''Build an iterator for all test cases'''
        for case in self.test_cases:
            case_spec_fullpath = os.path.join(self.project_root, case["path"],
                                              "TestCase.json")
            case_spec = json.load(open(case_spec_fullpath))
            yield {
                "id": case["path"],
                "path": case["path"],
                "fullpath": os.path.join(self.project_root, case["path"]),
                "test_vector": case["test_vector"],
                "spec": case_spec
            }

    def count_cases(self):
        return len(self.test_cases)


