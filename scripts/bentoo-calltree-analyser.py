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


def find_first_of(contents, candidates):
    for c in candidates:
        try:
            i = contents.index(c)
        except ValueError:
            i = -1
        if i >= 0:
            return (c, i)
    return (None, -1)


def column_split(columns):
    '''Split data column from index column in a data table'''
    # This function uses the following huristics: a data table begins with
    # conseqtive index columns, followed by consequtive data columns. Data
    # collector and transformers shall gurantee this.
    timer_index = find_first_of(columns, ["TimerName", "Name"])
    if not timer_index[0]:
        raise ValueError("Can not find timer column")
    procid_index = find_first_of(columns, ["ProcId"])
    threadid_index = find_first_of(columns, ["ThreadId"])
    split_index = max(timer_index[1], procid_index[1], threadid_index[1])
    assert(split_index >= 0)
    split_index += 1
    return (columns[0:split_index], columns[split_index:])


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


def build_abs_seq_map(calltree):
    result = {}
    level = {}
    seq_obj = {"seq": 0}

    def visit_tree(tree, curr_level=0):
        level[tree["id"]] = curr_level
        result[tree["id"]] = seq_obj["seq"]
        seq_obj["seq"] += 1
        for i, x in enumerate(tree["children"]):
            visit_tree(x, curr_level+1)

    visit_tree(calltree)
    return (result, level)


def compute_percentage(ref_db, calltree_file, out_db,
                       columns=None, append=None, treelize_timer_name=False):
    conn0 = sqlite3.connect(ref_db)

    ref_columns = extract_column_names(conn0)
    index_columns, data_columns = column_split(ref_columns)
    if columns:
        for x in columns:
            assert(x in data_columns)
        data_columns = list(columns)
    append_columns = []
    if append:
        append_columns.extend(append)
    timer_column = find_first_of(ref_columns, ["TimerName", "Name"])[0]
    if not timer_column:
        raise ValueError("Can not find timer column")
    index_columns.remove(timer_column)
    data_columns.insert(0, timer_column)

    calltree = json.load(file(calltree_file))
    timer_names = extract_timer_names(calltree)

    sql = map(quote, index_columns + data_columns + append_columns)
    sql = "SELECT %s FROM result WHERE " % ", ".join(sql)
    sql += " OR ".join("%s = \"%s\"" % (timer_column, x) for x in timer_names)
    sql += " ORDER BY %s" % ", ".join(map(quote, index_columns))
    data = pandas.read_sql_query(sql, conn0)

    parents = build_parent_map(calltree)
    abs_seq, level = build_abs_seq_map(calltree)
    top_timer = calltree["id"]

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

        def treelize(x):
            return "|" + "--" * level[x] + " " + x
        result["abs_seq"] = [abs_seq[x] for x in result[timer_column]]
        if treelize_timer_name:
            result[timer_column] = map(treelize, result[timer_column])
        else:
            result["level"] = [level[x] for x in result[timer_column]]
            result["parent"] = [parents[x] for x in result[timer_column]]

        return result

    final = []
    for k, v in data.groupby(index_columns):
        transformed = compute_group_percent(v)
        final.append(transformed)
    final = pandas.concat(final, ignore_index=True)

    conn1 = sqlite3.connect(out_db)
    final.to_sql("result", conn1, if_exists="replace", index=False)

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
    parser.add_argument("-a", "--append", nargs="+", default=[],
                        help="Append these columns (no compute)")
    parser.add_argument("--treelize-timer-name", action="store_true",
                        help="Create a pretty tree repr for timer names")

    args = parser.parse_args()
    compute_percentage(**vars(args))


if __name__ == "__main__":
    main()
