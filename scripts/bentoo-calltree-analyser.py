#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#

'''
bentoo-calltree-analyser.py - Bottleneck analysis based on calltree

This tool computes relative/absolute percentage for selected events based on
calltree structure.
'''

import sqlite3
import argparse
import pandas
import fnmatch
import re
import json
import sys


def glob_strings(source, patterns):
    if not source or not patterns:
        return []
    return [x for x in source for y in patterns if fnmatch.fnmatch(x, y)]


def quote(string):
    return "\"%s\"" % string


def is_data_column(column):
    if re.match(r"\w+:\w+", column):
        return True
    if column in ["RDTSC", "CallCount"]:
        return True
    return False


def extract_column_names(conn, table="result"):
    orig_row_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    r = conn.execute("SELECT * FROM %s LIMIT 1" % table).fetchone()
    names = list(r.keys())
    conn.row_factory = orig_row_factory
    return names


def extract_timer_names(calltree):
    timers = set()

    def visit_tree(node):
        timers.add(node["id"])
        for x in node["children"]:
            visit_tree(x)

    visit_tree(calltree)
    return list(timers)


def build_parent_map(calltree):
    parents = {}

    def visit_tree(tree, top_level=False):
        if top_level:
            parents[tree["id"]] = None
        for x in tree["children"]:
            parents[x["id"]] = tree["id"]
            visit_tree(x)

    visit_tree(calltree, top_level=True)
    return parents


def build_seq_map(calltree):
    seq = {}

    def visit_tree(tree, top_level=False):
        if top_level:
            seq[tree["id"]] = 0
        for i, x in enumerate(tree["children"]):
            seq[x["id"]] = i
            visit_tree(x)

    visit_tree(calltree, top_level=True)
    return seq


def compute_percentage(ref_db, calltree_file, out_db,
                       columns=None, timer_column="TimerName"):
    conn0 = sqlite3.connect(ref_db)

    ref_columns = extract_column_names(conn0)
    index_columns = [x for x in ref_columns if not is_data_column(x)]
    data_columns = [x for x in ref_columns if is_data_column(x)]
    if columns:
        for x in columns:
            assert(x in data_columns)
        data_columns = list(columns)
    index_columns.remove(timer_column)
    data_columns.insert(0, timer_column)

    calltree = json.load(file(calltree_file))
    timer_names = extract_timer_names(calltree)

    sql = map(quote, index_columns + data_columns)
    sql = "SELECT %s FROM result WHERE " % ", ".join(sql)
    sql += " OR ".join("%s = \"%s\"" % (timer_column, x) for x in timer_names)
    sql += " ORDER BY %s" % ", ".join(map(quote, index_columns))
    data = pandas.read_sql_query(sql, conn0)

    parents = build_parent_map(calltree)
    seq = build_seq_map(calltree)
    top_timer = timer_names[0]

    def compute_group_percent(group):
        result = pandas.DataFrame(group)
        for c in data_columns:
            if c == timer_column:
                continue
            values = {}
            for k, v in parents.iteritems():
                if k == top_timer:
                    values[k] = group[group[timer_column] == k][c].max()
                else:
                    values[k] = group[group[timer_column] == v][c].max()
            top_value = values[top_timer]
            abs_c = "%s_abs_percent" % c
            rel_c = "%s_rel_percent" % c
            result[abs_c] = result[c] / top_value
            result[rel_c] = [values[x] for x in result[timer_column]]
            result[rel_c] = result[c] / result[rel_c]
        result["parent"] = [parents[x] for x in result[timer_column]]
        result["sequence"] = [seq[x] for x in result[timer_column]]
        sys.exit(0)
        return result

    data = data.groupby(index_columns).apply(compute_group_percent)

    conn1 = sqlite3.connect(out_db)
    data.to_sql("result", conn1, if_exists="replace", index=False)

    conn1.close()
    conn0.close()


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ref_db",
                        help="Database to provide raw data")
    parser.add_argument("calltree_file",
                        help="Calltree file")
    parser.add_argument("out_db",
                        help="Database to store output")
    parser.add_argument("-c", "--columns", nargs="+", default=[],
                        help="Compute only these columns")
    parser.add_argument("--timer-column", default="TimerName",
                        help="Column name for timer names")

    args = parser.parse_args()
    compute_percentage(**vars(args))


if __name__ == "__main__":
    main()
