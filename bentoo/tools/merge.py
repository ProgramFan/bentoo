#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
'''
bentoo-merger.py - merge performance data from different sources

This tool merges collected performance data from different data sources. It
understands the internal structure of performance database and selects merge
keys automatically. Currently, it only supports data generated by Likwid
parser.
'''

from builtins import map
from builtins import zip
import argparse
import sqlite3
import fnmatch
import pandas
import re


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


def split_columns(columns):
    '''split 'columns' into (index_columns, data_columns)'''
    timer_column_index = columns.index("TimerName")
    return (columns[:timer_column_index + 1], columns[timer_column_index + 1:])


def extract_column_names(conn, table="result"):
    orig_row_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    r = conn.execute("SELECT * FROM %s LIMIT 1" % table).fetchone()
    names = list(r.keys())
    conn.row_factory = orig_row_factory
    return names


def merge_db(main_db,
             ref_db,
             out_db,
             replace=None,
             append=None,
             replace_with=None):
    conn0 = sqlite3.connect(main_db)
    conn1 = sqlite3.connect(ref_db)

    main_cols = extract_column_names(conn0)
    ref_cols = extract_column_names(conn1)

    if replace_with:
        replace_cols = [x.split("=")[0] for x in replace_with]
        replace_refs = [x.split("=")[1] for x in replace_with]
    else:
        replace_cols = glob_strings(main_cols, replace)
    append_cols = glob_strings(ref_cols, append)
    index_cols, _ = split_columns(ref_cols)

    if replace_with:
        index_sql = ", ".join(map(quote, index_cols))
        replace_sql = ", ".join("\"{0}\" AS \"{1}\"".format(x, y)
                                for x, y in zip(replace_refs, replace_cols))
        append_sql = ", ".join(map(quote, append_cols))
        sql = [index_sql, replace_sql, append_sql]
        sql = [x for x in sql if x]
        sql = "SELECT %s FROM result" % ", ".join(sql)
    else:
        sql = index_cols + replace_cols + append_cols
        sql = list(map(quote, sql))
        sql = "SELECT %s FROM result" % ", ".join(sql)
    ref_data = pandas.read_sql_query(sql, conn1)
    ref_data = ref_data.set_index(index_cols)
    main_data = pandas.read_sql_query("SELECT * FROM result", conn0)
    main_data = main_data.set_index(index_cols)
    for x in append_cols:
        assert (x not in main_data)
        main_data[x] = 0
    main_data.update(ref_data)

    conn2 = sqlite3.connect(out_db)
    # IMPORTANT: use flattern index so index=False in to_sql works properly,
    # i.e, dataframe index is ignored.
    main_data = main_data.reset_index()
    main_data.to_sql("result", conn2, if_exists="replace", index=False)
    conn2.commit()
    conn2.close()

    conn1.close()
    conn0.close()


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("main_db", help="Database to be updated")
    parser.add_argument("ref_db", help="Database to get update data")
    parser.add_argument("out_db", help="Database to store output")
    parser.add_argument(
        "-a",
        "--append",
        nargs="+",
        default=None,
        help="Columns to append, supports shell wildcards")
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument(
        "-r",
        "--replace",
        nargs="+",
        default=None,
        help="Columns to replace, supports shell wildcards ")
    grp.add_argument(
        "-w",
        "--replace-with",
        action="append",
        default=[],
        help="Replace column x with y (format: x=y)")

    args = parser.parse_args()
    merge_db(**vars(args))


if __name__ == "__main__":
    main()
