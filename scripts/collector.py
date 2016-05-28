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
import glob
import csv
import cStringIO
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

class TestProjectReader(object):

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
        self.test_cases = conf["test_cases"]
        self.data_files = conf.get("data_files", [])

    def itercases(self):
        for case in self.test_cases:
            case_spec_fullpath = os.path.join(
                self.project_root,
                case["path"],
                "TestCase.json")
            case_spec = json.load(file(case_spec_fullpath))
            yield {
                "id": case["path"],
                "test_vector": case["test_vector"],
                "fullpath": os.path.join(self.project_root, case["path"]),
                "spec": case_spec
            }

    def count_cases(self):
        return len(self.test_cases)


class FnmatchFilter(object):

    def __init__(self, patterns, mode="include"):
        assert(mode in ("include", "exclude"))
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

    def __init__(self, project_root, case_filter=None, filter_mode="include",
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
                result_selector = xrange(len(result_files))
            for result_id in result_selector:
                fn = os.path.join(fullpath, result_files[result_id])
                short_fn = os.path.relpath(fn, self.project.project_root)
                if not os.path.exists(fn):
                    print("WARNING: Result file '%s' not found" % short_fn)
                    continue
                spec = zip(self.project.test_factors + ["result_id"],
                           case["test_vector"] + [result_id])
                spec = OrderedDict(spec)
                yield {"spec": spec, "fullpath": fn}


#
# DataParser
#


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

    table_id = 0
    content = file(fn, "r").read()
    logtbl_ptn = re.compile(
        "^\+{80}$(?P<name>.*?)^\+{80}$" + ".*?(?P<header>^.*?$)" +
        "(?P<content>.*?)^\+{80}$", re.M + re.S)
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

    def __init__(self, args):
        pass

    def itertables(self, fn):
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
        "Overhead": float,
        "LocalMaxTime": float,
        "LocalAvgTime": float,
        "MaxLoc": int,
        "LocalMaxLoc": int,
    }

    table_id = 0
    content = file(fn, "r").read()
    logtbl_ptn = re.compile(
        r"^\*+ (?P<name>.*?) \*+$\n-{10,}\n" + r"^(?P<header>^.*?$)\n-{10,}\n"
        + r"(?P<content>.*?)^-{10,}\n", re.M + re.S)
    for match in logtbl_ptn.finditer(content):
        # TODO: use column width to better split columns. the columns names and
        # width can be determined from the header, everything is right aligned.
        log_table = match.groupdict()
        table_name = log_table["name"]
        # Extract table header
        header = log_table["header"].split()
        assert(header[0] == "Name")
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
            timer_rec["Name"] = timer_name.strip()
            timer_values = ln[timer_value_pos:]
            seg_ptn = re.compile(r"(\S+)")
            for i, seg in enumerate(seg_ptn.finditer(timer_values)):
                cn = header[i + 1]
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

    def __init__(self, args):
        pass

    def itertables(self, fn):
        return parse_jasmin4log(fn)


class UnifiedJasminParser(object):

    @staticmethod
    def register_cmd_args(argparser):
        pass

    @staticmethod
    def retrive_cmd_args(namespace):
        return {}

    def __init__(self, args):
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
                return "null"

        def null_parse(fn):
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
        return self.parser_funcs[self.filetype_detector(fn)](fn)


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
                while not self.match_start(iterable.next()):
                    continue
                line = iterable.next()
                while not self.match_end(line):
                    block.append(line)
                    line = iterable.next()
                yield block
            except StopIteration:
                return

    def findblock(self, iterable):
        block = []
        while not self.match_start(iterable.next()):
            continue
        line = iterable.next()
        while not self.match_end(line):
            block.append(line)
            line = iterable.next()
        return block


class EventsetParser(object):

    def __init__(self):
        self.events = {}
        self.counters = {}

    def process(self, iterable):
        for line in iterable:
            counter, event = line.split()
            combined = "%s:%s" % (event, counter)
            self.events[combined] = event
            self.counters[combined] = counter


class MetricsParser(object):

    def __init__(self):
        self.metrics = []

    def process(self, iterable):
        for line in iterable:
            if re.findall(r"\[.*\]", line):
                name, unit, formula = map(lambda x: x.strip(),
                                          re.match(r"^(.*?)\[(.*?)\](.*)$",
                                                   line).groups())
                self.metrics.append((name, unit, formula))
            else:
                name, formula = map(lambda x: x.strip(),
                                    re.match(r"^(.*?)(\S+)$", line).groups())
                self.metrics.append((name, "1", formula))


class LikwidMetrics(object):

    def __init__(self, group_file):
        with open(groupdef) as groupfile:
            eventset_reader = BlockReader("EVENTSET\n", "\n")
            metrics_reader = BlockReader("METRICS\n", "\n")
            ep = EventsetParser()
            mp = MetricsParser()
            ep.process(eventset_reader.findblock(groupfile))
            mp.process(metrics_reader.findblock(groupfile))
            self.eventset = {"events": ep.events, "counters": ep.counters}
            self.metrics = mp.metrics

    def counter_name(self, fullname):
        return self.eventset["counters"][fullname]

    def event_name(self, fullname):
        return self.eventset["events"][fullname]

    def metric_count(self):
        return len(self.metrics)

    def metric_name(self, metric_id):
        return self.metrics[metric_id][0]

    def metric_unit(self, metric_id):
        return self.metrics[metric_id][1]

    def calc_metric(self, metric_id, eventvals):
        formula = str(self.metrics[metric_id][2])
        for k, v in eventvals.iteritems():
            formula = formula.replace(k, str(v))
        return eval(formula)


def locate_likwid_group_file(arch, group):
    possible_places = os.environ["PATH"].split(":")
    possible_places.append("/usr/local/bin")
    possible_places.append("/usr/local/likwid/bin")
    possible_places.append("/home/lib/jasmin/thirdparty/likwid/bin")
    for p in possible_places:
        if os.path.exists(os.path.join(p, "likwid-perfctr")):
            likwid_home = os.path.basename(p)
            break
    raise RuntimeError("Can not find likwid.")

    return os.path.join(likwid_home, "share", "likwid", "perfgroups",
                        arch, group + ".txt")


class LikwidOutputParser(object):

    def __init__(self, group, group_file):
        self.likwid = None
        self.group = group
        self.column_names = []
        self.column_types = []
        self.data = []
        self.group_file = group_file

    def process(self, iterable):
        line1 = iterable.next()
        line2 = iterable.next()
        cpu_model = line1.split(":")[-1].strip()
        cpu_cycles = line2.split(":")[-1].strip()
        if not self.likwid:
            # OPTIMIZATION: init likwid metrics only once
            group_file_path = self.group_file
            if group_file_path == "auto" or not os.path.exists(group_file):
                group_file_path = locate_likwid_group_file(cpu_model,
                                                           self.group)
            likwid = LikwidMetrics(group_file_path)
            # OPTIMIZATION: calculate table structure only once
            self.column_names.extend(["TimerName", "ThreadId", "RDTSC",
                                      "CallCount"])
            self.column_types.extend([str, int, float, int])
            for i in xrange(likwid.metric_count()):
                name = likwid.metric_name(i).replace(" ", "_")
                self.column_names.append(name)
                self.column_types.append(float)
            self.likwid = likwid
        self.data = []
        other = [x for x in iterable]
        other = cStringIO.StringIO("".join(other[1:-1]))
        for record in csv.DictReader(other):
            tmp = {k.split(":")[-1]: v for k, v in record.iteritems()}
            tmp["time"] = tmp["RDTSC"]
            tmp["inverseClock"] = 1.0 / float(cpu_cycles)
            result = [tmp["RegionTag"], tmp["ThreadId"], tmp["RDTSC"],
                      tmp["CallCount"]]
            for i in xrange(self.likwid.metric_count()):
                value = self.likwid.calc_metric(i, tmp)
                result.append(value)
            self.data.append(result)


class LikwidParser(object):

    @staticmethod
    def register_cmd_args(argparser):
        argparser.add_argument("--likwid-group-file", default="auto",
                               help="Performance group file (default: auto)")

    @staticmethod
    def retrive_cmd_args(namespace):
        return {
            "group_file": namespace.likwid_group_file
        }

    def __init__(self, args):
        self.args = args

    def itertables(self, fn):
        # We only accept fake file "LIKWID_${GROUP}", so check it.
        filename = os.path.basename(fn)
        if not filename.startswith("LIKWID_"):
            raise RuntimeError(
                "Invalid data file '%s', shall be 'LIKWID_${GROUP}'" % fn)
        likwid_group = filename[7:]
        # Search for real likwid data file, it shall be of regex
        # 'likwid_counters.\d+.dat'
        result_dir = os.path.dirname(fn)
        likwid_data = glob.glob(os.path.join(result_dir,
                                             "likwid_counters.*.dat"))
        if not likwid_data:
            return

        files = [file(path) for path in likwid_data]

        parser = LikwidOutputParser(likwid_group, self.group_file)
        likwid_block = BlockReader("@start_likwid\n", "@end_likwid\n")
        # Count blocks to ease table_id generating
        nblocks = len(likwid_block.iterblocks(files[0]))
        if nblocks == 0:
            return
        # Reset files[0] as iterblocks have already arrive eof.
        files[0] = file(likwid_data[0])

        for table_id in xrange(nblocks):
            data = []
            for i, f in enumerate(files):
                proc_id = int(os.path.basename(likwid_data[i]).split(".")[1])
                block = likwid_block.findblock(f)
                assert(block)
                parser.process(likwid_block.findblock(f))
                for d in parser.data:
                    data.append([d[0], proc_id] + d[1:])
            cn = [parser.column_names[0], "ProcId"] + parser.column_names[1:]
            ct = [parser.column_types[0], int] + parser.column_types[1:]
            yield {
                "table_id": table_id,
                "column_names": cn,
                "column_types": ct,
                "data": data
            }


class ParserFactory(object):

    @staticmethod
    def create(name, namespace):
        if name == "jasmin3":
            return JasminParser(JasminParser.retrive_cmd_args(namespace))
        elif name == "jasmin4":
            return Jasmin4Parser(Jasmin4Parser.retrive_cmd_args(namespace))
        elif name == "jasmin":
            return UnifiedJasminParser(
                UnifiedJasminParser.retrive_cmd_args(namespace))
        elif name == "likwid":
            return LikwidParser(LikwidParser.retrive_cmd_args(namespace))
        else:
            raise ValueError("Unsupported parser: %s" % name)

    @staticmethod
    def register_cmd_args(argparser):
        group = argparser.add_argument_group("Jasmin Parser Arguments")
        JasminParser.register_cmd_args(group)
        group = argparser.add_argument_group("Jasmin4 Parser Arguments")
        Jasmin4Parser.register_cmd_args(group)
        group = argparser.add_argument_group("Unified Jasmin Parser Arguments")
        UnifiedJasminParser.register_cmd_args(group)
        group = argparser.add_argument_group("Likwid Parser Arguments")
        LikwidParser.register_cmd_args(group)


#
# StorageBackend
#


class SqliteSerializer(object):
    typemap = {
        None: "NULL",
        int: "INTEGER",
        long: "INTEGER",
        float: "REAL",
        str: "TEXT",
        unicode: "TEXT",
        buffer: "BLOB"
    }

    @staticmethod
    def register_cmd_args(argparser):
        pass

    @staticmethod
    def retrive_cmd_args(namespace):
        return {}

    def __init__(self, dbfile, args):
        conn = sqlite3.connect(dbfile)
        obj = conn.execute("DROP TABLE IF EXISTS result")
        conn.commit()
        self.conn = conn

    def serialize(self, data_items, column_names, column_types):
        '''Dump content to database
        '''
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
        argparser.add_argument("--pandas-format", default="xlsx",
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
            raise RuntimeError(
                "Unsupported output format '%s'" % self.file_format)


class SerializerFactory(object):

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
        group = argparser.add_argument_group("Sqlite3 Serializer Arguments")
        SqliteSerializer.register_cmd_args(group)
        group = argparser.add_argument_group("Pandas Serializer Arguments")
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
        assert(filter_mode in ("include", "exclude"))
        self.filter = FnmatchFilter(column_filter, filter_mode)

    def aggregate(self, tables):
        if type(tables) is list:
            tables = iter(tables)
        # Probe table structure
        try:
            first_table = next(tables)
        except StopIteration:
            return None

        table_id = first_table["id"]
        table_content = first_table["content"]
        all_names = table_id.keys() + table_content["column_names"]
        all_types = [type(x) for x in table_id.values()]
        all_types.extend(table_content["column_types"])

        ds = [i for i, n in enumerate(all_names) if self.filter.valid(n)]
        column_names = [all_names[i] for i in ds]
        column_types = [all_types[i] for i in ds]

        def data_generator():
            table_id = first_table["id"]
            for item in first_table["content"]["data"]:
                all_values = table_id.values() + item
                yield [all_values[i] for i in ds]
            for table in tables:
                table_id = table["id"]
                for item in table["content"]["data"]:
                    all_values = table_id.values() + item
                    yield [all_values[i] for i in ds]

        return {
            "column_names": column_names,
            "column_types": column_types,
            "data": data_generator()
        }


class Collector(object):

    def __init__(self):
        pass

    def collect(self, scanner, parser, aggregator, serializer):
        def table_geneartor():
            for data_file in scanner.iterfiles():
                file_spec = data_file["spec"]
                for tbl in parser.itertables(data_file["fullpath"]):
                    spec = OrderedDict(file_spec)
                    spec["table_id"] = tbl["table_id"]
                    yield {"id": spec, "content": tbl}
        final_table = aggregator.aggregate(table_geneartor())
        serializer.serialize(final_table["data"],
                             final_table["column_names"],
                             final_table["column_types"])


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project_root", help="Test project root directory")
    parser.add_argument("data_file", help="Data file to save results")

    group = parser.add_argument_group("Scanner Arguments")
    grp = group.add_mutually_exclusive_group()
    grp.add_argument("-i", "--include", default=None, nargs="+",
                     metavar="CASE_PATH",
                     help="Include only matched cases (shell wildcards)")
    grp.add_argument("-e", "--exclude", default=None, nargs="+",
                     metavar="CASE_PATH",
                     help="Excluded matched cases (shell wildcards)")
    group.add_argument("--use-result", default=[0], nargs="+",
                       metavar="RESULT_ID",
                       help="Choose result files to use (as index)")

    group = parser.add_argument_group("Parser Arguments")
    group.add_argument("-p", "--parser", default="jasmin",
                       choices=["jasmin3", "jasmin4", "jasmin", "likwid"],
                       help="Parser for raw result files (default: jasmin)")
    group.add_argument("--use-table", default=None, nargs="+",
                       metavar="TABLE_ID",
                       help="Choose which data table to use (as index)")
    ParserFactory.register_cmd_args(parser)

    group = parser.add_argument_group("Aggregator Arguments")
    grp = group.add_mutually_exclusive_group()
    grp.add_argument("-d", "--drop-columns", default=None, nargs="+",
                     metavar="COLUMN_NAME",
                     help="Drop un-wanted table columns")
    grp.add_argument("-k", "--keep-columns", default=None, nargs="+",
                     metavar="COLUMN_NAME",
                     help="Keep only speciied table columns")

    group = parser.add_argument_group("Serializer Arguments")
    group.add_argument("-s", "--serializer",
                       choices=["sqlite3", "pandas"], default="sqlite3",
                       help="Serializer to dump results (default: sqlite3)")
    SerializerFactory.register_cmd_args(parser)

    args = parser.parse_args()

    # make scanner
    if args.include:
        case_filter = args.include
        filter_mode = "include"
    elif args.exclude:
        case_filter = args.include
        filter_mode = "exclude"
    else:
        case_filter = None
        filter_mode = "exclude"
    use_result = map(int, args.use_result)
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
    collector.collect(scanner, parser, aggregator, serializer)

if __name__ == "__main__":
    main()
