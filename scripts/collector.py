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
            "column_names": header,
            "column_types": types,
            "data": data
        }
        yield table


class JasminParser:

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
            "column_names": header,
            "column_types": types,
            "data": data
        }

        yield table


class Jasmin4Parser:

    def itertables(self, fn):
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

    def process(self, iterable, consumer):
        def content(iterable):
            while not self.match_start(iterable.next()):
                continue
            line = iterable.next()
            while not self.match_end(line):
                yield line
                line = iterable.next()
        consumer.process(content(iterable))


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

    @classmethod
    def locate_group(cls, likwid_home, arch, group):
        path = os.path.join(likwid_home, "share", "likwid", "perfgroups", arch,
                            "%s.txt" % group)
        return path if os.path.exists(path) else None

    def __init__(self, likwid_home, arch, group):
        groupdef = self.locate_group(likwid_home, arch, group)
        if not groupdef:
            raise RuntimeError("Can not find group '%s' for '%s' in '%s'"
                               % (group, arch, likwid_home))
        with open(groupdef) as groupfile:
            eventset_reader = BlockReader("EVENTSET\n", "\n")
            metrics_reader = BlockReader("METRICS\n", "\n")
            ep = EventsetParser()
            mp = MetricsParser()
            eventset_reader.process(groupfile, ep)
            metrics_reader.process(groupfile, mp)
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


def guess_likwid_home():
    possible_places = os.environ["PATH"].split(":")
    possible_places.append("/usr/local/bin")
    possible_places.append("/usr/local/likwid/bin")
    possible_places.append("/home/lib/jasmin/thirdparty/likwid/bin")
    for p in possible_places:
        if os.path.exists(os.path.join(p, "likwid-perfctr")):
            return os.path.dirname(p)
    raise RuntimeError("Can not find likwid.")


class LikwidOutputParser(object):

    def __init__(self, group):
        self.likwid = None
        self.group = group
        self.column_names = []
        self.column_types = []
        self.data = []

    def process(self, iterable):
        line1 = iterable.next()
        line2 = iterable.next()
        cpu_model = line1.split(":")[-1].strip()
        cpu_cycles = line2.split(":")[-1].strip()
        if not self.likwid:
            # OPTIMIZATION: init likwid metrics only once
            likwid = LikwidMetrics(guess_likwid_home(), cpu_model, self.group)
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
    def __init__(self, *args, **kwargs):
        pass

    def itertables(self, fn):
        # Likwid output one file for each process, so we construct the list of
        # all files to workaround the result specificaiton limit.
        result_dir = os.path.dirname(fn)
        likwid_data = glob.glob(os.path.join(result_dir,
                                             "likwid_counters.*.dat"))
        likwid_group = os.path.basename(fn).split("LIKWID_")[1]
        assert(likwid_data)
        files = [file(path) for path in likwid_data]

        parser = LikwidOutputParser(likwid_group)
        likwid_block = BlockReader("@start_likwid\n", "@end_likwid\n")
        # we only support the first table currently
        data = []
        for i, f in enumerate(files):
            proc_id = int(os.path.basename(likwid_data[i]).split(".")[1])
            likwid_block.process(f, parser)
            for d in parser.data:
                data.append([d[0], proc_id] + d[1:])
        cnames = [parser.column_names[0], "ProcId"] + parser.column_names[1:]
        ctypes = [parser.column_types[0], int] + parser.column_types[1:]
        yield {
            "column_names": cnames,
            "column_types": ctypes,
            "data": data
        }


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

    def __init__(self, dbfile):
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

    def __init__(self, data_file, file_format=None):
        self.data_file = data_file
        self.file_format = file_format if file_format else "xlsx"

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


class TableColumnFilter(object):

    def __init__(self, column_names, filter_spec, action="throw"):
        assert action in ("throw", "keep")
        self.column_names = column_names
        self.action = action
        if not filter_spec:
            self.filter_mask = None
            return
        from fnmatch import fnmatchcase
        parsed_spec = [x.strip() for x in filter_spec.split(",")]
        filter_mask = [reduce(lambda x, y: x or y,
                              [fnmatchcase(n, x) for x in parsed_spec])
                       for n in self.column_names]
        self.filter_mask = filter_mask

    def filter(self, data_row):
        # short cut for empty filter
        if not self.filter_mask:
            return data_row
        if self.action == "keep":
            return [data_row[i] for i, t in enumerate(self.filter_mask) if t]
        elif self.action == "throw":
            return [data_row[i] for i, t in enumerate(self.filter_mask)
                    if not t]
        else:
            raise RuntimeError("Bad filter action '%s'" % self.action)


def make_parser(name, *args, **kwargs):
    if name == "jasmin3":
        return JasminParser(*args, **kwargs)
    elif name == "jasmin4":
        return Jasmin4Parser(*args, **kwargs)
    elif name == "jasmin":
        return UnifiedJasminParser(*args, **kwargs)
    elif name == "likwid":
        return LikwidParser(*args, **kwargs)
    else:
        raise ValueError("Unsupported parser: %s" % name)


def make_serializer(name, *args, **kwargs):
    if name == "sqlite3":
        return SqliteSerializer(*args, **kwargs)
    elif name == "pandas":
        return PandasSerializer(*args, **kwargs)
    else:
        raise ValueError("Unsupported serializer: %s" % name)


class Collector(object):

    '''TestResultCollector - Collect test results and save them'''

    def __init__(self, project_root, data_file, parser, serializer,
                 drop_columns=None, use_table=None):
        self.project = TestProjectReader(project_root)
        self.parser = make_parser(parser)
        self.serializer = make_serializer(serializer, data_file)
        self.use_table = use_table
        self.drop_columns = drop_columns

    @staticmethod
    def _table_generator(project, parser, table_selector=None):
        for case in project.itercases():
            case_path = case["path"]
            # TODO: support collecting from multiple result file. This
            # would require another column designating the filename. This
            # is not often used, so shall be used as an option
            result_fn = os.path.join(case_path, case["spec"]["results"][0])
            short_fn = os.path.relpath(result_fn, project.project_root)
            if not os.path.exists(result_fn):
                print "WARNING: Result file '%s' not found" % short_fn
                continue
            content = list(parser.itertables(result_fn))
            if not content:
                print "WARNING: No timer table found in '%s'" % short_fn
                continue
            test_vector = OrderedDict(zip(project.test_factors,
                                          case["test_vector"]))

            if not table_selector or not isinstance(table_selector, int):
                for table_id, data_table in enumerate(content):
                    yield {
                        "test_vector": test_vector,
                        "data_table": data_table,
                        "table_id": table_id
                    }
            else:
                try:
                    data_table = content[table_selector]
                except IndexError:
                    print "WARNING: Table %s not found in '%s'" % (
                        table_selector, short_fn)
                    yield {
                        "test_vector": test_vector,
                        "data_table": data_table,
                        "table_id": table_selector
                    }

    @staticmethod
    def _data_item_generator(table):
        test_vector_values = table["test_vector"].values()
        table_id = table["table_id"]
        data_table = table["data_table"]
        for data_row in data_table["data"]:
            yield test_vector_values + [table_id] + data_row

    def collect(self):
        table_producer = iter(self._table_generator(self.project, self.parser,
                                                    self.use_table))

        # Build final data table structure
        try:
            ref_table = next(table_producer)
        except StopIteration:
            # nothing to collect, return
            return
        ref_vector = ref_table["test_vector"]
        ref_data = ref_table["data_table"]
        column_names = ref_vector.keys() + \
            ["table_id"] + ref_data["column_names"]
        column_types = map(type, ref_vector.values())  # types of test factors
        column_types.append(int)  # type of table id
        column_types.extend(ref_data["column_types"])  # types of table columns

        column_dropper = TableColumnFilter(column_names, self.drop_columns,
                                           action="throw")
        column_names = column_dropper.filter(column_names)
        column_types = column_dropper.filter(column_types)

        def data_row_producer():
            for item in self._data_item_generator(ref_table):
                yield column_dropper.filter(item)
            for table in table_producer:
                for item in self._data_item_generator(table):
                    yield column_dropper.filter(item)

        self.serializer.serialize(data_row_producer(), column_names,
                                  column_types)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "project_root", help="Test project root directory")
    parser.add_argument("data_file", help="Data file to save results")
    parser.add_argument("-s", "--serializer", metavar="SERIALIZER",
                        dest="serializer", choices=["sqlite3", "pandas"],
                        default="sqlite3",
                        help="Serializer to dump results (default: sqlite3)")
    parser.add_argument("-p", "--parser", metavar="PARSER", dest="parser",
                        choices=["jasmin3", "jasmin4", "jasmin", "likwid"],
                        default="jasmin",
                        help="Parser for raw result files (default: jasmin)")
    parser.add_argument("--use-table", type=int, default=None,
                        help="Choose which data table to use")
    parser.add_argument("-d", "--drop-columns", default=None, metavar="SPEC",
                        dest="drop_columns",
                        help="Drop un-wanted table columns")

    args = parser.parse_args()
    collector = Collector(args.project_root, args.data_file, args.parser,
                          args.serializer, args.drop_columns, args.use_table)
    collector.collect()

if __name__ == "__main__":
    main()
