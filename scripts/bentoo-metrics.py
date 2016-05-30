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
import argparse
import sqlite3
import fnmatch
from collections import OrderedDict
from functools import reduce


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
        self.events = []
        self.counters = []

    def process(self, iterable):
        for line in iterable:
            counter, event = line.split()
            self.events.append(event)
            self.counters.append(counter)


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
        with open(group_file) as groupfile:
            eventset_reader = BlockReader("EVENTSET\n", "\n")
            metrics_reader = BlockReader("METRICS\n", "\n")
            ep = EventsetParser()
            mp = MetricsParser()
            ep.process(eventset_reader.findblock(groupfile))
            mp.process(metrics_reader.findblock(groupfile))
            self.eventset = {"events": ep.events, "counters": ep.counters,
                             "pair": ["%s:%s" % x for x in zip(ep.events,
                                                               ep.counters)]}
            self.metrics = mp.metrics

    def event_count(self):
        return len(self.eventset["events"])

    def event_name(self, event_id):
        return self.eventset["events"][event_id]

    def counter_name(self, event_id):
        return self.eventset["counters"][event_id]

    def event_counter_pair(self, event_id):
        return self.eventset["pair"][event_id]

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
    for p in possible_places:
        if os.path.exists(os.path.join(p, "likwid-perfctr")):
            likwid_home = os.path.dirname(p)
            path = os.path.join(likwid_home, "share", "likwid", "perfgroups",
                                arch, group + ".txt")
            if not os.path.exists(path):
                raise RuntimeError("Bad likwid installation: can not find "
                                   "'%s' for '%s'" % (group, arch))
            return path
    raise RuntimeError("Can not find likwid.")


def do_process(data_file, output_file, aggregate="no"):
    conn = sqlite3.connect(data_file)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Discover the structure of input database
    sql = "select * from result limit 1"
    r = conn.execute(sql).fetchone()
    input_keys = r.keys()
    input_types = [type(x) for x in r]

    # Aggregate on thread
    aggregate_axis = ["ThreadId", "ProcId"]

    # build select heading
    def is_value_key(k):
        if k in ("RDTSC", "CallCount"):
            return True
        if re.match(r"\w+:\w", k):
            # match the "CPU_CYC_HALT:FIXC0" event counter
            return True
        return False
    select = []
    group_by = []
    if aggregate == "no":
        select = ["\"%s\"" % k for k in input_keys]
        group_by = [k for k in input_keys if not is_value_key(k)]
    elif aggregate == "thread":
        for k in input_keys:
            if k == "ThreadId":
                select.append("COUNT(ThreadId) AS ThreadCount")
            if k == "RDTSC":
                select.append("SUM(RDTSC) AS SumRDTSC")
                select.append("MAX(RDTSC) AS MaxRDTSC")
            elif k == "CallCount":
                select.append("SUM(CallCount) AS SumCallCount")
            elif re.match(r"\w+:\w+", k):
                select.append("SUM(\"{0}\") AS \"{0}\"".format(k))
            else:
                select.append(k)
                # group by all remaining non value keys
                group_by.append("\"%s\"" % k)
    elif aggregate == "proc_thread":
        for k in input_keys:
            if k == "ProcId":
                select.append("COUNT(ProcId) AS ProcCount")
            elif k == "ThreadId":
                select.append("COUNT(ThreadId) AS ThreadCount")
            elif k == "RDTSC":
                select.append("SUM(RDTSC) AS SumRDTSC")
                select.append("MAX(RDTSC) AS MaxRDTSC")
            elif k == "CallCount":
                select.append("SUM(CallCount) AS SumCallCount")
            elif re.match(r"\w+:\w+", k):
                select.append("SUM(\"{0}\") AS \"{0}\"".format(k))
            else:
                select.append(k)
                # group by all remaining non value keys
                group_by.append("\"%s\"" % k)

    select = ", ".join(select)
    group_by = ", ".join(group_by)

    sql = "SELECT {0} FROM result GROUP BY {1}".format(select, group_by)
    cursor.execute(sql)
    result = [list(r) for r in conn.execute(sql).fetchall()]
    import pprint
    pprint.pprint(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_file",
                        help="Database containing raw event values")
    parser.add_argument("output_file",
                        help="Database to store calculated metrics")
    parser.add_argument("--aggregate", default="thread",
                        choices=["no", "thread", "proc_thread"],
                        help="Data aggregation (default: thread)")

    args = parser.parse_args()
    do_process(**vars(args))


if __name__ == "__main__":
    main()
