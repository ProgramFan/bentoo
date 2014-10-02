#!/usr/bin/env python2.7
#
# Tool to collect test results and save them into a database
#

import os
import sys
import re
import string
import argparse
import json
from collections import OrderedDict


def parse_jasminlog(fn):
    '''parse_jasminlog - jasmin time manager log parser

    This function parses jasmin timer manager performance reports. It
    splits detected jasmin timer logs into several measures and assign
    them unique names.

    Assume the following log::

      ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
      TOTAL
      WALLCLOCK TIME
      ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
      Timer Name                                       Proc: 0     Max
      alg::NumericalIntegratorComponent::computing()   3.55 (100%) 7.3(90%)
      ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

    Examples
    --------

    The use of this function is fairly straight forward:
    >>> info = parse_jasminlog("demo_jasminlog.txt")
    >>> info[-1]["data"][0]["timer_name"]
    TOTAL_RUN_TIME
    >>> info[-1]["data"][0]["summed"]
    5.14626

    '''

    def tokenlize(s):
        '''Convert string into a valid lower case pythonic token'''
        invalid_chars = ":-+*/#\n"
        trans_table = string.maketrans(invalid_chars, " "*len(invalid_chars))
        return "_".join(map(string.lower, s.translate(trans_table).split()))

    avail_types = {
        "timer_name": str,
        "proc_0": float,
        "proc_0_percent": float,
        "summed": float,
        "summed_percent": float,
        "max": float,
        "max_percent": float,
        "proc": int
    }
    content = file(fn, "r").read()
    logtbl_ptn = re.compile("^\+{80}$(?P<name>.*?)^\+{80}$"
                            + ".*?(?P<header>^.*?$)"
                            + "(?P<content>.*?)^\+{80}$", re.M+re.S)
    result = []
    for match in logtbl_ptn.finditer(content):
        log_table = match.groupdict()
        table_name = tokenlize(log_table["name"])
        # We only handle table "TOTAL WALLCLOCK TIME"
        if table_name != "total_wallclock_time":
            continue
        # Extract table header
        header_ptn = re.compile(r"(Timer Name|Proc: \d+|Summed|Proc|Max)")
        header = map(tokenlize, header_ptn.findall(log_table["header"]))
        # Parse table rows
        table_contents = []
        for ln in log_table["content"].strip().split("\n"):
            rec_ptn = re.compile(r"^\s*(TOTAL RUN TIME:|\S+)\s*(.*)$")
            tl, tr = rec_ptn.search(ln).groups()
            timer_name = tl.strip()
            if timer_name == "TOTAL RUN TIME:":
                timer_name = "TOTAL_RUN_TIME"
            timer_rec = {"timer_name": avail_types["timer_name"](timer_name)}
            flt_ptn = r"[-+]?(?:\d+(?:\.\d*)?)(?:[Ee][-+]?\d+)?"
            seg_ptn = re.compile(r"({0})\s*(\({0}%\))?".format(flt_ptn))
            for i, seg in enumerate(seg_ptn.finditer(tr)):
                # Example: 99.9938 (97%)
                a, b = seg.groups()
                cn = header[i + 1]
                timer_rec[cn] = avail_types[cn](a)
                if b:
                    pn = "{0}_percent".format(cn)
                    timer_rec[pn] = avail_types[pn](b[1:-2]) * 0.01
            table_contents.append(timer_rec)
        # Fix table header when there are XX% records
        for k in table_contents[0].iterkeys():
            if k not in header:
                header.append(k)
        # Make final result
        types = {x: avail_types[x] for x in header}
        table = {"columns": header, "column_types": types,
                 "data": table_contents}
        result.append(table)
    return result


def parse_jasmin4log(fn):
    '''parse_jasmin4log - jasmin 4.0 time manager log parser

    This function parses jasmin 4.0 timer manager performance reports. It
    splits detected jasmin timer logs into several measures and assign
    them unique names.

    Assume the following log::

    *************************** TIME STATISTICS  ****************************
    -------------------------------------------------------------------------
                                                       Name           MaxTime
    -------------------------------------------------------------------------
                                             TOTAL RUN TIME   0.9065(100.00%)
    algs::SimpleHierarchyTimeIntegrator::advanceHierarchy()    0.8624(95.14%)
    -------------------------------------------------------------------------

    Examples
    --------

    The use of this function is fairly straight forward:
    >>> info = parse_jasmin4log("demo_jasmin4log.txt")
    >>> info[-1]["data"][0]["Name"]
    TOTAL RUN TIME
    >>> info[-1]["data"][0]["Accesses"]
    1

    '''

    avail_types = {
        "Name": str,
        "MaxTime": float,
        "MaxTime_percent": float,
        "AvgTime": float,
        "AvgTime_percent": float,
        "LoadBalance": float,
        "Accesses": int,
        "Overhead": float
    }
    content = file(fn, "r").read()
    logtbl_ptn = re.compile(r"^\*+ (?P<name>.*?) \*+$\n-{10,}\n"
                            + r"^(?P<header>^.*?$)\n-{10,}\n"
                            + r"(?P<content>.*?)^-{10,}\n", re.M+re.S)
    result = []
    for match in logtbl_ptn.finditer(content):
        log_table = match.groupdict()
        table_name = log_table["name"]
        # Extract table header
        header = log_table["header"].split()
        # Parse table rows
        table_contents = []
        for ln in log_table["content"].strip().split("\n"):
            timer_rec = {}
            seg_ptn = re.compile(r"(TOTAL RUN TIME|\S+)")
            for i, seg in enumerate(seg_ptn.finditer(ln)):
                cn = header[i]
                val = seg.group(1)
                flt_ptn = r"[-+]?(?:\d+(?:\.\d*)?)(?:[Ee][-+]?\d+)?|[+-]?nan"
                m = re.match(r"({0})\(({0})%\)".format(flt_ptn), val)
                if m:
                    pn = "{0}_percent".format(cn)
                    a, b = map(float, [m.group(1), m.group(2)])
                    b = b * 0.01
                    timer_rec[cn], timer_rec[pn] = a, b
                    continue
                m = re.match(r"({0})%".format(flt_ptn), val)
                if m:
                    timer_rec[cn] = float(m.group(1)) * 0.01
                    continue
                timer_rec[cn] = avail_types[cn](val)
            table_contents.append(timer_rec)
        # Fix table header when there are XX% records
        for k in table_contents[0].iterkeys():
            if k not in header:
                header.append(k)
        # Make final result
        types = {x: avail_types[x] for x in header}
        table = {"columns": header, "column_types": types,
                 "data": table_contents}
        result.append(table)
    return result


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", help="Directory for test project")
    parser.add_argument("result_file", help="Result filename")
    parser.add_argument("--format", default="sqlite3", action="store",
                        help="File format for result database")

    args = parser.parse_args()
    project = TestProjectScanner(args.project_dir)
    info = project.scan()

    all_results = []
    for case in info["cases"]:
        result_dir = os.path.join(info["root"], *case["vpath"].values())
        result_file = os.path.join(result_dir, case["spec"]["results"][0])
        content = parse_jasminlong(result_file)
        all_results.append((case["vpath"], content))

    print all_results


if __name__ == "__main__":
    main()
