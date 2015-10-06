#!/usr/bin/env python2.7
#
'''Collector - Test results collector

Collector scans a test project directory, parses all result files found and
saves all parsed results as a self-described data sheet in a file. One can then
use Analyser or other tools to investigate the resultant data sheet.

To use collector, simply following the argument document. To use the generated
data sheet, keep in mind that the data sheet is ralational database table alike
and the concrete format is backend specific. For sqlite3 backend, the result is
stored in a table named 'result'. The data sheet is designed to be easily
parsable by pandas, so the recommendation is to use pandas to investigate the
data.
'''

import os
import sys
import re
import string
import argparse
import json
import sqlite3
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
        version = conf.get("version", 1)
        if version != 1:
            raise RuntimeError(
                "Unsupported project version '%s': Only 1 " % version)
        self.name = conf["name"]
        self.test_factors = conf["test_factors"]
        self.data_files = conf["data_files"]
        self.test_cases = conf["test_cases"]

    def itercases(self):
        for case in self.test_cases:
            case_spec_fullpath = os.path.join(
                self.project_root,
                case["path"],
                "TestCase.json")
            case_spec = json.load(file(case_spec_fullpath))
            yield {
                "test_vector": case["test_vector"],
                "path": os.path.join(self.project_root, case["path"]),
                "spec": case_spec
            }

    def count_cases(self):
        return len(self.test_cases)


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
        trans_table = string.maketrans(invalid_chars, " " * len(invalid_chars))
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
    logtbl_ptn = re.compile(
        "^\+{80}$(?P<name>.*?)^\+{80}$" + ".*?(?P<header>^.*?$)" +
        "(?P<content>.*?)^\+{80}$", re.M + re.S)
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
        table = {
            "columns": header,
            "column_types": types,
            "data": table_contents
        }
        result.append(table)
    return result


class JasminParser:
    def parse(self, fn):
        return parse_jasminlog(fn)


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
    logtbl_ptn = re.compile(
        r"^\*+ (?P<name>.*?) \*+$\n-{10,}\n" + r"^(?P<header>^.*?$)\n-{10,}\n"
        + r"(?P<content>.*?)^-{10,}\n", re.M + re.S)
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
        table = {
            "columns": header,
            "column_types": types,
            "data": table_contents
        }
        result.append(table)
    return result


class Jasmin4Parser:
    def parse(self, fn):
        return parse_jasmin4log(fn)


class UnifiedJasminParser:
    def __init__(self):
        jasmin4_ptn = re.compile(
            r"^\*+ (?P<name>.*?) \*+$\n-{10,}\n" +
            r"^(?P<header>^.*?$)\n-{10,}\n" + r"(?P<content>.*?)^-{10,}\n",
            re.M + re.S)
        jasmin3_ptn = re.compile(
            "^\+{80}$(?P<name>.*?)^\+{80}$" + ".*?(?P<header>^.*?$)" +
            "(?P<content>.*?)^\+{80}$", re.M + re.S)

        def detector(fn):
            content = file(fn).read()
            if jasmin3_ptn.search(content):
                return "jasmin3"
            elif jasmin4_ptn.search(content):
                return "jasmin4"
            else:
                msg = "File %s is neither jasmin 3 nor jasmin 4 log" % fn
                raise RuntimeError(msg)

        self.filetype_detector = detector
        self.parser_funcs = {
            "jasmin3": parse_jasminlog,
            "jasmin4": parse_jasmin4log
        }

    def parse(self, fn):
        return self.parser_funcs[self.filetype_detector(fn)](fn)


class SqliteSerializer:
    typemap = {
        None: "NULL",
        int: "INTEGER",
        long: "INTEGER",
        float: "REAL",
        str: "TEXT",
        unicode: "TEXT",
        buffer: "BLOB"
    }

    def __init__(self, db):
        conn = sqlite3.connect(db)
        obj = conn.execute("DROP TABLE IF EXISTS result")
        conn.commit()
        self.conn = conn

    def serialize(self, columns, column_types, data):
        # Build table creation and insertion SQL statements
        table_columns = []
        for c in columns:
            t = column_types.get(c, str)
            assert t in SqliteSerializer.typemap
            tn = SqliteSerializer.typemap[t]
            table_columns.append("{0} {1}".format(c, tn))
        table_columns_sql = ", ".join(table_columns)
        create_table_sql = "CREATE TABLE result ({0})".format(
            table_columns_sql)
        ph_sql = ", ".join(["?"] * len(columns))
        insert_row_sql = "INSERT INTO result VALUES ({0})".format(ph_sql)
        # Create table and insert data items
        cur = self.conn.cursor()
        cur.execute(create_table_sql)
        for item in data:
            assert isinstance(item, list) or isinstance(item, tuple)
            assert len(item) == len(columns)
            cur.execute(insert_row_sql, item)
        self.conn.commit()
        self.conn.close()


class TestResultCollector:
    '''TestResultCollector - Collect test results and save them'''

    def __init__(self, serializer):
        self.serializer = serializer

    def collect(self, project_root, parser):
        project = TestProjectReader(project_root)
        all_results = []
        for case in project.itercases():
            case_path = case["case_path"]
            # TODO: support collecting from multiple result file
            result_fn = os.path.join(case_path, case["run_spec"]["results"][0])
            if not os.path.exists(result_fn):
                continue
            content = parser.parse(result_fn)
            all_results.append((case["test_vector"], content))

        def data_item_generator():
            for test_vector, content in all_results:
                # Only use the last record, TODO: use all records
                data = content[-1]
                for row in data["data"]:
                    row_list = [row.get(x, None) for x in data["columns"]]
                    yield test_vector.values() + row_list

        ref_vector, ref_content = all_results[0]
        columns = ref_vector.keys()
        column_types = {x: type(ref_vector[x]) for x in ref_vector.keys()}
        for c in ref_content[0]["columns"]:
            columns.append(c)
            column_types[c] = ref_content[0]["column_types"].get(c, str)

        self.serializer.serialize(columns, column_types, data_item_generator())


def make_parser(name, *args, **kwargs):
    if name == "jasmin3":
        return JasminParser(*args, **kwargs)
    elif name == "jasmin4":
        return Jasmin4Parser(*args, **kwargs)
    elif name == "jasmin":
        return UnifiedJasminParser(*args, **kwargs)
    else:
        raise ValueError("Unsupported parser: %s" % name)


def make_serializer(name, *args, **kwargs):
    if name == "sqlite3":
        return SqliteSerializer(*args, **kwargs)
    else:
        raise ValueError("Unsupported serializer: %s" % name)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project_root", help="Test project root directory")
    parser.add_argument("data_file", help="Data file to save results")
    parser.add_argument("--serializer",
                        choices=["sqlite3"],
                        default="sqlite3",
                        help="Serializer to dump results (default: sqlite3)")
    parser.add_argument("--parser",
                        choices=["jasmin3", "jasmin4", "jasmin"],
                        default="jasmin",
                        help="Parser for raw result files (default: jasmin)")

    args = parser.parse_args()
    parser = make_parser(args.parser)
    serializer = make_serializer(args.serializer, args.data_file)
    collector = TestResultCollector(serializer)
    collector.collect(args.project_root, parser)


if __name__ == "__main__":
    main()
