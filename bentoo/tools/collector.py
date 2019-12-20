#!/usr/bin/env python
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
from __future__ import print_function, unicode_literals

import os
import sys
import re
import string
import argparse
import json
import sqlite3
import glob
import csv
import io
import fnmatch
import tarfile
from collections import OrderedDict
from functools import reduce

#
# Design Of Collector
#
# Collector consists of ResultScanner, DataParser, DataAggregator and
# StorageBackend.  ResultScanner searches the test project for resultant data
# files, and generates a list of file paths (absolute path). DataParser parses
# each data file to generate a list of data tables. Each file shall contain the
# same number of data tables, and all data tables shall have the same shape.
# DataAggregator merge all or selected data tables into a large data table,
# dropping table columns if required. The StorageBackend is then responsible
# for storing the resultant data table.
#
# The ResultScanner, DataParser and StorageBackend is implemented using
# duck-typing to support multiple types of parsers and backends.
#

#
# ResultScanner
#

from bentoo.common.project import TestProjectReader


class FnmatchFilter(object):
    def __init__(self, patterns, mode="include"):
        assert (mode in ("include", "exclude"))
        self.patterns = patterns

        def match_any(path, patterns):
            for m in patterns:
                if fnmatch.fnmatch(path, m):
                    return True
            return False

        def null_check(path):
            return True

        def include_check(path):
            return True if match_any(path, self.patterns) else False

        def exclude_check(path):
            return False if match_any(path, self.patterns) else True

        if not patterns:
            self.checker = null_check
        elif mode == "include":
            self.checker = include_check
        else:
            self.checker = exclude_check

    def valid(self, input):
        return self.checker(input)


class ResultScanner(object):
    def __init__(self,
                 project_root,
                 case_filter=None,
                 filter_mode="include",
                 result_selector=None):
        '''
        Parameters
        ----------

        project_root: string, root dir of the test project
        case_filter: list of strings, wildcard strings to match cases
        filter_mode: "include" or "exclude", how the filter is handled
        result_selector: list of integers, index of selected results
        '''
        self.project = TestProjectReader(project_root)
        self.case_filter = FnmatchFilter(case_filter, filter_mode)
        self.result_selector = result_selector

    def iterfiles(self):
        for case in self.project.itercases():
            if not self.case_filter.valid(case["id"]):
                continue
            fullpath = case["fullpath"]
            result_files = case["spec"]["results"]
            result_selector = self.result_selector
            if not result_selector:
                result_selector = range(len(result_files))
            for result_id in result_selector:
                fn = os.path.join(fullpath, result_files[result_id])
                short_fn = os.path.relpath(fn, self.project.project_root)
                if not os.path.exists(fn):
                    print("WARNING: Result file '%s' not found" % short_fn)
                    continue
                spec = list(
                    zip(self.project.test_factors + ["result_id"],
                        case["test_vector"] + [result_id]))
                spec = OrderedDict(spec)
                yield {"spec": spec, "fullpath": fn, "short_fn": short_fn}


#
# DataParser
#


def parse_jasminlog(fn, use_table=None):
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
        invalid_chars = r"[:-+*/#\n]"
        return "_".join(
            map(lambda x: x.lower(),
                re.sub(invalid_chars, " ", s).split()))

    avail_types = {
        "TimerName": str,
        "proc_0": float,
        "proc_0_percent": float,
        "summed": float,
        "summed_percent": float,
        "max": float,
        "max_percent": float,
        "proc": int
    }

    table_id = 0
    content = open(fn, "r").read()
    logtbl_ptn = re.compile(
        r"^\+{80}$(?P<name>.*?)^\+{80}$" + ".*?(?P<header>^.*?$)" +
        r"(?P<content>.*?)^\+{80}$", re.M + re.S)
    for match in logtbl_ptn.finditer(content):
        log_table = match.groupdict()
        table_name = tokenlize(log_table["name"])
        # We only handle table "TOTAL WALLCLOCK TIME"
        if table_name != "total_wallclock_time":
            continue
        # skipping tables not wanted, but null use_table means use all tables
        if use_table and table_id not in use_table:
            continue
        # Extract table header
        header_ptn = re.compile(r"(Timer Name|Proc: \d+|Summed|Proc|Max)")
        header = list(map(tokenlize, header_ptn.findall(log_table["header"])))
        assert (header[0] == "timer_name")
        header[0] = "TimerName"
        # Parse table rows
        table_contents = []
        for ln in log_table["content"].strip().split("\n"):
            rec_ptn = re.compile(r"^\s*(TOTAL RUN TIME:|\S+)\s*(.*)$")
            tl, tr = rec_ptn.search(ln).groups()
            timer_name = tl.strip()
            if timer_name == "TOTAL RUN TIME:":
                timer_name = "TOTAL_RUN_TIME"
            timer_rec = {"TimerName": avail_types["TimerName"](timer_name)}
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
        for k in table_contents[0].keys():
            if k not in header:
                header.append(k)
        # Make final result:
        # Ensures `len(header) == len(types)` and `[len(data_item) ==
        # len(header) for data_item in data]`. So the data is in good shape.
        types = [avail_types[x] for x in header]
        data = [[v.get(k, None) for k in header] for v in table_contents]
        table = {
            "table_id": table_id,
            "column_names": header,
            "column_types": types,
            "data": data
        }
        yield table
        table_id += 1


class JasminParser(object):
    @staticmethod
    def register_cmd_args(argparser):
        pass

    @staticmethod
    def retrive_cmd_args(namespace):
        return {}

    def __init__(self, use_table, args):
        self.use_table = use_table

    def itertables(self, fn):
        tables = [t for t in parse_jasminlog(fn)]
        if not tables:
            yield
            return
        if self.use_table:
            for i in self.use_table:
                yield tables[i]
        else:
            for t in tables:
                yield t


def parse_jasmin4log(fn, use_table=None):
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
        "TimerName": str,
        "MaxTime": float,
        "MaxTime_percent": float,
        "AvgTime": float,
        "AvgTime_percent": float,
        "LoadBalance": float,
        "Accesses": int,
        "Overhead": float,
        "LocalMaxTime": float,
        "LocalAvgTime": float,
        "MaxLoc": int,
        "LocalMaxLoc": int,
    }

    table_id = 0
    content = open(fn, "r").read()
    logtbl_ptn = re.compile(
        r"^\*+ (?P<name>.*?) \*+$\n-{10,}\n" +
        r"^(?P<header>^.*?$)\n-{10,}\n" + r"(?P<content>.*?)^-{10,}\n",
        re.M + re.S)
    for match in logtbl_ptn.finditer(content):
        # skipping tables not wanted, but null use_table means use all tables
        if use_table and table_id not in use_table:
            continue
        # TODO: use column width to better split columns. the columns names and
        # width can be determined from the header, everything is right aligned.
        log_table = match.groupdict()
        # Extract table header
        header = log_table["header"].split()
        assert (header[0] == "Name")
        header[0] = "TimerName"
        timer_name_pos = log_table["header"].index("Name")
        timer_value_pos = timer_name_pos + len("Name")
        # Parse table rows
        table_contents = []
        for ln in log_table["content"].split("\n"):
            # skip empty lines
            if not ln.strip():
                continue
            timer_rec = {}
            # split out the timer name column first, it may contain strange
            # charactors such as spaces.
            timer_name = ln[:timer_value_pos]
            timer_rec["TimerName"] = timer_name.strip()
            timer_values = ln[timer_value_pos:]
            seg_ptn = re.compile(r"(\S+)")
            for i, seg in enumerate(seg_ptn.finditer(timer_values)):
                cn = header[i + 1]
                val = seg.group(1)
                flt_ptn = r"[-+]?(?:\d+(?:\.\d*)?)(?:[Ee][-+]?\d+)?|[+-]?nan"
                m = re.match(r"({0})\(({0})%\)".format(flt_ptn), val)
                if m:
                    pn = "{0}_percent".format(cn)
                    a, b = list(map(float, [m.group(1), m.group(2)]))
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
        for k in table_contents[0].keys():
            if k not in header:
                header.append(k)
        # Make final result
        # Ensures `len(header) == len(types)` and `[len(data_item) ==
        # len(header) for data_item in data]`. So the data is in good shape.
        types = [avail_types.get(x, str) for x in header]
        data = [[v.get(k, None) for k in header] for v in table_contents]
        table = {
            "table_id": table_id,
            "column_names": header,
            "column_types": types,
            "data": data
        }

        yield table
        table_id += 1


class Jasmin4Parser(object):
    @staticmethod
    def register_cmd_args(argparser):
        pass

    @staticmethod
    def retrive_cmd_args(namespace):
        return {}

    def __init__(self, use_table, args):
        self.use_table = use_table

    def itertables(self, fn):
        tables = [t for t in parse_jasmin4log(fn)]
        if not tables:
            yield
            return
        if self.use_table:
            for i in self.use_table:
                yield tables[i]
        else:
            for t in tables:
                yield t


class UnifiedJasminParser(object):
    @staticmethod
    def register_cmd_args(argparser):
        pass

    @staticmethod
    def retrive_cmd_args(namespace):
        return {}

    def __init__(self, use_table, args):
        self.use_table = use_table
        jasmin4_ptn = re.compile(
            r"^\*+ (?P<name>.*?) \*+$\n-{10,}\n" +
            r"^(?P<header>^.*?$)\n-{10,}\n" + r"(?P<content>.*?)^-{10,}\n",
            re.M + re.S)
        jasmin3_ptn = re.compile(
            r"^\+{80}$(?P<name>.*?)^\+{80}$" + ".*?(?P<header>^.*?$)" +
            r"(?P<content>.*?)^\+{80}$", re.M + re.S)

        def detector(fn):
            content = open(fn).read()
            if jasmin3_ptn.search(content):
                return "jasmin3"
            elif jasmin4_ptn.search(content):
                return "jasmin4"
            else:
                return "null"

        def null_parse(fn, use_table):
            # return + yield makes a perfect empty generator function
            return
            yield

        self.filetype_detector = detector
        self.parser_funcs = {
            "jasmin3": parse_jasminlog,
            "jasmin4": parse_jasmin4log,
            "null": null_parse
        }

    def itertables(self, fn):
        filetype = self.filetype_detector(fn)
        tables = [t for t in self.parser_funcs[filetype](fn)]
        if not tables:
            yield
            return
        if self.use_table:
            for i in self.use_table:
                yield tables[i]
        else:
            for t in tables:
                yield t


#
# Likwid Parser
#


class BlockReader(object):
    def __init__(self, start, end, use_regex=False):
        if use_regex:
            self.start_ = re.compile(start)

            def match_start(x):
                return self.start_.match(x)

            self.match_start = match_start

            self.end = re.compile(end)

            def match_end(x):
                return self.end_.match(x)

            self.match_end = match_end
        else:

            def match_start(x):
                return x == self.start_

            def match_end(x):
                return x == self.end_

            self.start_ = start
            self.end_ = end
            self.match_start = match_start
            self.match_end = match_end

    def iterblocks(self, iterable):
        while True:
            try:
                block = []
                while not self.match_start(next(iterable)):
                    continue
                line = next(iterable)
                while not self.match_end(line):
                    block.append(line)
                    line = next(iterable)
                yield block
            except StopIteration:
                return

    def findblock(self, iterable):
        block = []
        while not self.match_start(next(iterable)):
            continue
        line = next(iterable)
        while not self.match_end(line):
            block.append(line)
            line = next(iterable)
        return block


class LikwidBlockParser(object):
    def __init__(self):
        self.column_names = []
        self.column_types = []
        self.data = []

    def clear(self):
        self.column_names = []
        self.column_types = []
        self.data = []

    def process(self, iterable):
        self.clear()
        next(iterable)
        line2 = next(iterable)
        cpu_cycles = float(line2.split(":")[-1].strip())
        other = [x for x in iterable]
        other = io.StringIO("".join(other[1:-1]))
        likwid_data = csv.DictReader(other)
        # NOTE: likwid output use RegionTag as TimerName, as well as a
        # different order. We fix it here.
        start_columns = "ThreadId,TimerName,time,CallCount,inverseClock".split(
            ",")
        self.column_names.extend(start_columns)
        self.column_types.extend([int, str, float, int, float])
        other_columns = list(likwid_data.fieldnames[4:])
        other_columns = [x for x in other_columns if x]
        self.column_names.extend(other_columns)
        self.column_types.extend([float] * len(other_columns))
        self.data = []
        for record in likwid_data:
            result = [
                record["ThreadId"], record["RegionTag"], record["RDTSC"],
                record["CallCount"]
            ]
            result.append(1.0 / cpu_cycles)
            result.extend(record[f] for f in other_columns)
            self.data.append(result)


class LikwidParser(object):
    @staticmethod
    def register_cmd_args(argparser):
        pass

    @staticmethod
    def retrive_cmd_args(namespace):
        return {}

    def __init__(self, use_table, args):
        self.args = args
        self.use_table = use_table

    def itertables(self, fn):
        # We only accept fake file "LIKWID_${GROUP}", so check it.
        filename = os.path.basename(fn)
        if not filename.startswith("LIKWID_"):
            raise RuntimeError(
                "Invalid data file '%s', shall be 'LIKWID_${GROUP}'" % fn)
        # Search for real likwid data file, it shall be of regex
        # 'likwid_counters.\d+.dat'
        result_dir = os.path.dirname(fn)
        likwid_data = glob.glob(
            os.path.join(result_dir, "likwid_counters.*.dat"))
        if not likwid_data:
            print("WARNING: No likwid data file found in '%s'" % result_dir)
            return

        files = [open(path) for path in likwid_data]

        parser = LikwidBlockParser()
        likwid_block = BlockReader("@start_likwid\n", "@end_likwid\n")
        # Count blocks to ease table_id generating
        nblocks = len(list(likwid_block.iterblocks(files[0])))
        if nblocks == 0:
            print("WARNING: No likwid data table found in '%s'" %
                  likwid_data[0])
            return
        # Reset files[0] as iterblocks have already arrive eof.
        files[0] = open(likwid_data[0])

        all_tables = []
        for table_id in range(nblocks):
            data = []
            for i, f in enumerate(files):
                proc_id = int(os.path.basename(likwid_data[i]).split(".")[1])
                block = likwid_block.findblock(f)
                assert (block)
                parser.process(iter(block))
                for d in parser.data:
                    data.append([proc_id] + d)
            cn = ["ProcId"] + parser.column_names
            ct = [int] + parser.column_types
            all_tables.append({
                "table_id": table_id,
                "column_names": cn,
                "column_types": ct,
                "data": data
            })

        if not all_tables:
            yield
            return
        if self.use_table:
            for i in self.use_table:
                yield all_tables[i]
        else:
            for t in all_tables:
                yield t


class UdcBlockParser(object):
    def __init__(self):
        self.column_names = []
        self.column_types = []
        self.data = []

    def clear(self):
        self.column_names = []
        self.column_types = []
        self.data = []

    def process(self, iterable):
        self.clear()
        content = [x for x in iterable]
        content = io.StringIO("".join(content))
        data = csv.DictReader(content)
        start_columns = "ThreadId,TimerName".split(",")
        self.column_names.extend(start_columns)
        self.column_types.extend([int, str])
        other_columns = list(data.fieldnames[2:])
        other_columns = [x for x in other_columns if x]
        self.column_names.extend(other_columns)
        self.column_types.extend([float] * len(other_columns))
        self.data = []
        for record in data:
            result = [record["ThreadId"], record["TimerName"]]
            result.extend(record[f] for f in other_columns)
            self.data.append(result)


class UdcParser(object):
    @staticmethod
    def register_cmd_args(argparser):
        pass

    @staticmethod
    def retrive_cmd_args(namespace):
        return {}

    def __init__(self, use_table, args):
        self.args = args
        self.use_table = use_table

    def itertables(self, fn):
        # We only accept fake file "LIKWID_${GROUP}", so check it.
        filename = os.path.basename(fn)
        if filename != "USER_DEFINED_COUNTERS":
            raise ValueError(
                "Invalid data file '%s', shall be 'USER_DEFINED_COUNTERS'" %
                fn)
        # Search for real data file, it shall be of regex
        # 'user_defined_counters.\d+.dat'
        result_dir = os.path.dirname(fn)
        udc_data = glob.glob(
            os.path.join(result_dir, "user_defined_counters.*.dat"))
        if not udc_data:
            print("WARNING: No data file found in '%s'" % result_dir)
            return

        files = [open(path) for path in udc_data]

        parser = UdcBlockParser()
        block_reader = BlockReader("@start_udc\n", "@end_udc\n")
        # Count blocks to ease table_id generating
        nblocks = len(list(block_reader.iterblocks(files[0])))
        if nblocks == 0:
            print("WARNING: No udc data table found in '%s'" % udc_data[0])
            return
        # Reset files[0] as iterblocks have already arrive eof.
        files[0] = open(udc_data[0])

        all_tables = []
        for table_id in range(nblocks):
            data = []
            for i, f in enumerate(files):
                proc_id = int(os.path.basename(udc_data[i]).split(".")[1])
                block = block_reader.findblock(f)
                assert (block)
                parser.process(iter(block))
                for d in parser.data:
                    data.append([proc_id] + d)
            cn = ["ProcId"] + parser.column_names
            ct = [int] + parser.column_types
            all_tables.append({
                "table_id": table_id,
                "column_names": cn,
                "column_types": ct,
                "data": data
            })

        if not all_tables:
            yield
            return
        if self.use_table:
            for i in self.use_table:
                yield all_tables[i]
        else:
            for t in all_tables:
                yield t


def identifier(val):
    '''Convert a string to a valid c identifier'''
    a = re.sub(r"\W", "_", str(val).strip().lower())
    return re.sub(r"_+", "_", a.strip("_"))


class YamlParser(object):
    '''Yaml table parser.

    This parser parses yaml document blocks in a file and convert them to a list
    of data tables. Each yaml block starts with a line `---` and ends with
    another line of either `---` or `...`, and the contents shall be a dict or a
    list of dicts. For example:

        The performance results: (time in usecs):
        ---
        time: 13.3
        float_ops: 112343449
        men_reads: 11334349399
        mem_writes: 33449934
        ---
    '''
    @staticmethod
    def register_cmd_args(argparser):
        pass

    @staticmethod
    def retrive_cmd_args(namespace):
        return {}

    def __init__(self, use_table, args):
        self.args = args
        self.use_table = use_table

    def itertables(self, fn):
        import bentoo.yaml as yaml
        all_tables = []

        yamldoc_regex = re.compile(
            r"(?:^|\n)\s*---\s*\n(.+?)\n\s*(---|...)\s*\n", re.M + re.S)
        for i, match in enumerate(yamldoc_regex.finditer(open(fn).read())):
            content = yaml.safe_load(match.group(1))
            if isinstance(content, dict):
                # a single dict
                cn = list(map(identifier, list(content.keys())))
                vals = list(content.values())
                ct = [type(x) for x in vals]
                data = [vals]
            elif isinstance(content, list):
                # a list of dicts
                assert content
                cn = list(map(identifier, list(content[0].keys())))
                ct = [type(x) for x in content[0].values()]
                data = []
                for item in content:
                    assert set(cn) == set(item.keys())
                    val = [item[x] for x in cn]
                    data.append(val)
            else:
                raise RuntimeError(
                    "Unsupported yaml table: {}".format(content))
            all_tables.append({
                "table_id": i,
                "column_names": cn,
                "column_types": ct,
                "data": data
            })

        if not all_tables:
            yield
            return
        if self.use_table:
            for i in self.use_table:
                yield all_tables[i]
        else:
            for t in all_tables:
                yield t


def guess_type(data):
    '''Guess the best column types for a string table'''
    type_hierarchy = [int, float, str]  # start from int, str for all

    def promote_type(val, type_index):
        for i in range(type_index, len(type_hierarchy) + 1):
            t = type_hierarchy[i]
            try:
                t(val)
                return i
            except ValueError:
                continue

    # for each colum of each row, we promote the type to be able to represent
    # all values accurately.
    curr_types = [0] * len(data[0])
    for row in data:
        for i, val in enumerate(row):
            curr_types[i] = promote_type(val, curr_types[i])
    return [type_hierarchy[i] for i in curr_types]


class PipetableParser(object):
    '''Pipetable table parser.

    This parser parses markdown's pipe tables in a file and convert them to a
    list of data tables.

        The performance results: (time in usecs):

        | time | float_ops | mem_reads | mem_writes |
        |------|-----------|-----------|------------|
        | 13.3 | 334e5     | 3334456555| 334343434  |
    '''
    @staticmethod
    def register_cmd_args(argparser):
        pass

    @staticmethod
    def retrive_cmd_args(namespace):
        return {}

    def __init__(self, use_table, args):
        self.args = args
        self.use_table = use_table

    def itertables(self, fn):
        all_tables = []

        # We use a loose regex for pipe table: each table row shall begin with
        # `|` and end with `|` and seperate with other contents by new lines.
        # Note we match `\n` explicitly since we restrict each table row to one
        # line.
        table_regex = re.compile(r"(?:^|\n)" + r"(\s*\|.+\|\s*\n)" +
                                 r"\s*\|[-:| ]+\|\s*\n" +
                                 r"((?:\s*\|.+\|\s*\n)+)" + r"(?:\n|$)")
        for i, match in enumerate(table_regex.finditer(open(fn).read())):
            parse_row = lambda x: [
                y.strip() for y in x.strip().strip('|').split('|')
            ]
            header = match.group(1)
            content = match.group(2)
            header = parse_row(header)
            data = []
            for line in content.split('\n'):
                if line.strip():
                    row = parse_row(line.strip())
                    data.append(row)
            column_types = guess_type(data)
            real_data = []
            for row in data:
                real_data.append(
                    [column_types[i](v) for i, v in enumerate(row)])
            all_tables.append({
                "table_id": i,
                "column_names": header,
                "column_types": column_types,
                "data": real_data
            })

        if not all_tables:
            yield
            return
        if self.use_table:
            for i in self.use_table:
                yield all_tables[i]
        else:
            for t in all_tables:
                yield t


class DsvParser(object):
    '''Delimiter seperated values table parser.

    This parser parses dsv tables in a file and convert them to a list of data
    tables. The table is seperated from surrounding texts by line of `|={3,}`
    and the default delimiter is `,` for csv.

        The performance results: (time in usecs):

        |===
        time, float_ops, mem_reads, mem_writes
        13.3, 334e5, 3334456555, 334343434
        |===
    '''
    @staticmethod
    def register_cmd_args(argparser):
        argparser.add_argument(
            "--dsv-seperator",
            metavar="CHAR",
            dest="dsv_sep",
            default=",",
            help="regex seperator for dsv values (default: ',')")

    @staticmethod
    def retrive_cmd_args(namespace):
        return {"sep": namespace.csv_sep}

    def __init__(self, use_table=[], args={'sep': ','}):
        self.args = args
        self.use_table = use_table

    def itertables(self, fn):
        all_tables = []

        table_regex = re.compile(r"\s*\|={3,}\s*\n" + r"((?:[^|]+\n){2,})" +
                                 r"\s*\|={3,}\n")
        for i, match in enumerate(table_regex.finditer(open(fn).read())):
            parse_row = lambda x: [
                y.strip() for y in re.split(self.args['sep'], x.strip())
            ]
            content = match.group(1).split('\n')
            header = content[0]
            header = parse_row(header)
            data = []
            for line in content[1:]:
                if line.strip():
                    row = parse_row(line.strip())
                    data.append(row)
            column_types = guess_type(data)
            real_data = []
            for row in data:
                real_data.append(
                    [column_types[i](v) for i, v in enumerate(row)])
            all_tables.append({
                "table_id": i,
                "column_names": header,
                "column_types": column_types,
                "data": real_data
            })

        if not all_tables:
            yield
            return
        if self.use_table:
            for i in self.use_table:
                yield all_tables[i]
        else:
            for t in all_tables:
                yield t


class ParserFactory(object):
    @staticmethod
    def default_parser():
        return "jasmin"

    @staticmethod
    def available_parsers():
        return ("yaml", "pipetable", "jasmin", "jasmin3", "jasmin4", "likwid",
                "udc", "dsv")

    @staticmethod
    def create(name, namespace):
        use_table = list(map(int, namespace.use_table))
        if name == "jasmin3":
            args = JasminParser.retrive_cmd_args(namespace)
            return JasminParser(use_table, args)
        elif name == "jasmin4":
            args = Jasmin4Parser.retrive_cmd_args(namespace)
            return Jasmin4Parser(use_table, args)
        elif name == "jasmin":
            args = UnifiedJasminParser.retrive_cmd_args(namespace)
            return UnifiedJasminParser(use_table, args)
        elif name == "likwid":
            args = LikwidParser.retrive_cmd_args(namespace)
            return LikwidParser(use_table, args)
        elif name == "udc":
            args = UdcParser.retrive_cmd_args(namespace)
            return UdcParser(use_table, args)
        elif name == "yaml":
            args = YamlParser.retrive_cmd_args(namespace)
            return YamlParser(use_table, args)
        elif name == "pipetable":
            args = PipetableParser.retrive_cmd_args(namespace)
            return PipetableParser(use_table, args)
        elif name == "dsv":
            args = DsvParser.retrive_cmd_args(namespace)
            return DsvParser(use_table, args)
        else:
            raise ValueError("Unsupported parser: %s" % name)

    @staticmethod
    def register_cmd_args(argparser):
        group = argparser.add_argument_group("jasmin3 parser arguments")
        JasminParser.register_cmd_args(group)
        group = argparser.add_argument_group("jasmin4 parser arguments")
        Jasmin4Parser.register_cmd_args(group)
        group = argparser.add_argument_group("jasmin parser arguments")
        UnifiedJasminParser.register_cmd_args(group)
        group = argparser.add_argument_group("likwid parser arguments")
        LikwidParser.register_cmd_args(group)
        group = argparser.add_argument_group("udc parser arguments")
        UdcParser.register_cmd_args(group)
        group = argparser.add_argument_group("yaml parser arguments")
        YamlParser.register_cmd_args(group)
        group = argparser.add_argument_group("pipetable parser arguments")
        PipetableParser.register_cmd_args(group)
        group = argparser.add_argument_group("dsv parser arguments")
        DsvParser.register_cmd_args(group)


#
# StorageBackend
#


class SqliteSerializer(object):
    typemap = {
        type(None): "NULL",
        int: "INTEGER",
        int: "INTEGER",
        float: "REAL",
        str: "TEXT",
        str: "TEXT",
        bytes: "BLOB"
    }

    @staticmethod
    def register_cmd_args(argparser):
        pass

    @staticmethod
    def retrive_cmd_args(namespace):
        return {}

    def __init__(self, dbfile, args):
        self.dbfile = dbfile

    def serialize(self, data_items, column_names, column_types):
        '''Dump content to database
        '''
        conn = sqlite3.connect(self.dbfile)
        conn.execute("DROP TABLE IF EXISTS result")
        conn.commit()
        self.conn = conn
        # Build table creation and insertion SQL statements
        column_segs = []
        for i, column_name in enumerate(column_names):
            t = column_types[i]
            assert t in SqliteSerializer.typemap
            tn = SqliteSerializer.typemap[t]
            column_segs.append("\"{0}\" {1}".format(column_name, tn))
        create_columns_sql = ", ".join(column_segs)
        create_table_sql = "CREATE TABLE result ({0})".format(
            create_columns_sql)
        ph_sql = ", ".join(["?"] * len(column_names))
        insert_row_sql = "INSERT INTO result VALUES ({0})".format(ph_sql)
        # Create table and insert data items
        cur = self.conn.cursor()
        cur.execute(create_table_sql)
        for item in data_items:
            assert isinstance(item, list) or isinstance(item, tuple)
            assert len(item) == len(column_names)
            cur.execute(insert_row_sql, item)
        self.conn.commit()
        self.conn.close()


class PandasSerializer(object):
    @staticmethod
    def register_cmd_args(argparser):
        argparser.add_argument("--pandas-format",
                               default="xlsx",
                               choices=("xls", "xlsx", "csv"),
                               help="Output file format")

    @staticmethod
    def retrive_cmd_args(namespace):
        return {"format": namespace.pandas_format}

    def __init__(self, data_file, args):
        self.data_file = data_file
        self.file_format = args["format"]

    def serialize(self, data_items, column_names, column_types):
        import numpy
        import pandas
        # column_types is not used becuase numpy automatically deduce the best
        # type for each data item.
        data = numpy.array(list(data_items))
        frame = pandas.DataFrame(data, columns=column_names)
        if self.file_format == "xls" or self.file_format == "xlsx":
            frame.to_excel(self.data_file, index=False)
        elif self.file_format == "csv":
            frame.to_csv(self.data_file, index=False)
        else:
            raise RuntimeError("Unsupported output format '%s'" %
                               self.file_format)


class SerializerFactory(object):
    @staticmethod
    def default_serializer():
        return "sqlite3"

    @staticmethod
    def available_serializers():
        return ("sqlite3", "pandas")

    @staticmethod
    def create(name, namespace):
        if name == "sqlite3":
            args = SqliteSerializer.retrive_cmd_args(namespace)
            return SqliteSerializer(namespace.data_file, args)
        elif name == "pandas":
            args = PandasSerializer.retrive_cmd_args(namespace)
            return PandasSerializer(namespace.data_file, args)
        else:
            raise ValueError("Unsupported serializer: %s" % name)

    @staticmethod
    def register_cmd_args(argparser):
        group = argparser.add_argument_group("sqlite3 serializer arguments")
        SqliteSerializer.register_cmd_args(group)
        group = argparser.add_argument_group("pandas serializer arguments")
        PandasSerializer.register_cmd_args(group)


#
# DataAggragator
#
# DataAggregator iterates over a list of data tables, filters unwanted collums
# and merges the results into a large data table. The tables shall have the
# same column names and types. Each table is identified by a unique id, which
# itself is an OrderedDict. All ids also share the same keys in the same order.
#


class DataAggregator(object):
    def __init__(self, column_filter=None, filter_mode="include"):
        assert (filter_mode in ("include", "exclude"))
        self.filter = FnmatchFilter(column_filter, filter_mode)

    def aggregate(self, tables):
        if type(tables) is list:
            tables = iter(tables)
        # Probe table structure
        try:
            first_table = next(tables)
        except StopIteration:
            print("WARNING: No data tables found")
            return None

        table_id = first_table["id"]
        table_content = first_table["content"]
        all_names = list(table_id.keys()) + table_content["column_names"]
        all_types = [type(x) for x in list(table_id.values())]
        all_types.extend(table_content["column_types"])

        ds = [i for i, n in enumerate(all_names) if self.filter.valid(n)]
        column_names = [all_names[i] for i in ds]
        column_types = [all_types[i] for i in ds]

        def data_generator():
            table_id = first_table["id"]
            for item in first_table["content"]["data"]:
                all_values = list(table_id.values()) + item
                yield [all_values[i] for i in ds]
            for table in tables:
                table_id = table["id"]
                for item in table["content"]["data"]:
                    all_values = list(table_id.values()) + item
                    yield [all_values[i] for i in ds]

        return {
            "column_names": column_names,
            "column_types": column_types,
            "data": data_generator()
        }


class Collector(object):
    def __init__(self):
        pass

    def collect(self, scanner, parser, aggregator, serializer, archive):
        def table_geneartor():
            for data_file in scanner.iterfiles():
                file_spec = data_file["spec"]
                for tbl in parser.itertables(data_file["fullpath"]):
                    if not tbl:
                        continue
                    spec = OrderedDict(file_spec)
                    spec["table_id"] = tbl["table_id"]
                    yield {"id": spec, "content": tbl}

        final_table = aggregator.aggregate(table_geneartor())
        if not final_table:
            return
        serializer.serialize(final_table["data"], final_table["column_names"],
                             final_table["column_types"])

        if archive:
            fns = [(x["fullpath"], x["short_fn"]) for x in scanner.iterfiles()]
            with tarfile.open(archive, "w:gz") as tar:
                for full_fn, short_fn in fns:
                    if not os.path.exists(full_fn):
                        continue
                    arcname = os.path.join("result-files", short_fn)
                    tar.add(full_fn, arcname=arcname)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project_root", help="Test project root directory")
    parser.add_argument("data_file", help="Data file to save results")

    group = parser.add_argument_group("Scanner Arguments")
    grp = group.add_mutually_exclusive_group()
    grp.add_argument("-i",
                     "--include",
                     default=None,
                     nargs="+",
                     metavar="CASE_PATH",
                     help="Include only matched cases (shell wildcards)")
    grp.add_argument("-e",
                     "--exclude",
                     default=None,
                     nargs="+",
                     metavar="CASE_PATH",
                     help="Excluded matched cases (shell wildcards)")
    group.add_argument("--use-result",
                       default=[0],
                       nargs="+",
                       metavar="RESULT_ID",
                       help="Choose result files to use (as index)")

    group = parser.add_argument_group("Parser Arguments")
    group.add_argument("-p",
                       "--parser",
                       default=ParserFactory.default_parser(),
                       choices=ParserFactory.available_parsers(),
                       help="Parser for raw result files (default: jasmin)")
    group.add_argument("--use-table",
                       default=[],
                       nargs="+",
                       metavar="TABLE_ID",
                       help="Choose which data table to use (as index)")
    ParserFactory.register_cmd_args(parser)

    group = parser.add_argument_group("Aggregator Arguments")
    grp = group.add_mutually_exclusive_group()
    grp.add_argument("-d",
                     "--drop-columns",
                     default=None,
                     nargs="+",
                     metavar="COLUMN_NAME",
                     help="Drop un-wanted table columns")
    grp.add_argument("-k",
                     "--keep-columns",
                     default=None,
                     nargs="+",
                     metavar="COLUMN_NAME",
                     help="Keep only speciied table columns")

    group = parser.add_argument_group("Serializer Arguments")
    group.add_argument("-s",
                       "--serializer",
                       choices=SerializerFactory.available_serializers(),
                       default=SerializerFactory.default_serializer(),
                       help="Serializer to dump results (default: sqlite3)")
    SerializerFactory.register_cmd_args(parser)

    group = parser.add_argument_group("Archiver Arguments")
    group.add_argument("-a",
                       "--archive",
                       metavar="FILE",
                       dest="archive",
                       default=None,
                       help="Archive output to a zip file")

    args = parser.parse_args()

    # make scanner
    if args.include:
        case_filter = args.include
        filter_mode = "include"
    elif args.exclude:
        case_filter = args.exclude
        filter_mode = "exclude"
    else:
        case_filter = None
        filter_mode = "exclude"
    use_result = list(map(int, args.use_result))
    scanner = ResultScanner(args.project_root, case_filter, filter_mode,
                            use_result)
    # make parser
    parser = ParserFactory.create(args.parser, args)
    # make aggregator
    if args.keep_columns:
        column_filter = args.keep_columns
        filter_mode = "include"
    elif args.drop_columns:
        column_filter = args.drop_columns
        filter_mode = "exclude"
    else:
        column_filter = None
        filter_mode = "exclude"
    aggregator = DataAggregator(column_filter, filter_mode)
    # make serializer
    serializer = SerializerFactory.create(args.serializer, args)
    # assemble collector and do acutal collecting
    collector = Collector()
    collector.collect(scanner, parser, aggregator, serializer, args.archive)


if __name__ == "__main__":
    main()
