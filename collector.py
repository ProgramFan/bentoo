#!/usr/bin/env python2.7
#
# Tool to collect test results and save them into a database
#

import os
import sys
import re
import string
import argparse
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


def recursively_parse_config(project_root, dim_names, vpath, current_dir):
    fn = os.path.join(current_dir, "TestConfig.json")
    cfg = parse_json(fn)
    result = None
    if "sub_directories" in cfg:
        # For subdirectories, we support two grammars:
        # 1. simple list: [dir0, dir1, dir2, ...]
        # 2. descriptive dict:
        #    {"dimension": dim, "directories": [dir0, ...]}
        if isinstance(cfg["sub_directories"], list):
            dir_list = cfg["sub_directories"]
        elif isinstance(cfg["sub_directories"], dict):
            dir_list = cfg["sub_directories"]["directories"]
        else:
            errmsg = "Invalid sub_directories spec in '{0}'".format(fn)
            raise RuntimeError(errmsg)
        result = OrderedDict()
        for sub_dir in dir_list:
            p = os.path.join(current_dir, sub_dir)
            new_vpath = OrderedDict(vpath)
            vpath_key = dim_names[len(vpath)]
            new_vpath[vpath_key] = sub_dir
            r = recursively_parse_config(project_root, dim_names, new_vpath, p)
            result[sub_dir] = r
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


def scan_project(project_dir):
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", help="Directory for test project")

    args = parser.parse_args()
    content = parse_jasmin4log(args.project_dir)
    print content


if __name__ == "__main__":
    main()
