#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#


'''bentoo-aggregator - Aggregate per-core event values

This tool aggregates per-core event values to per-process or per-application
values. The input is a database of per-core values (so ProcId and ThreadId
column is required). The output is a database of per-proc or per-application
values. Some columns such as time are specially treated to maintain capability
with existing metric calculation tools.
'''

import os
import re
import argparse
import sqlite3


SQLITE_TYPE = {
    type(None): "NULL",
    int: "INTEGER",
    long: "INTEGER",
    float: "REAL",
    str: "TEXT",
    unicode: "TEXT",
    buffer: "BLOB"
}


def split_columns(columns):
    '''split 'columns' into (index_columns, data_columns)'''
    timer_column_index = columns.index("TimerName")
    return (columns[:timer_column_index+1], columns[timer_column_index+1:])


def quote(x):
    return "\"{}\"".format(x)


def aggregate(input_db, output_db, on="thread"):
    conn0 = sqlite3.connect(input_db)
    conn0.row_factory = sqlite3.Row

    # Discover the structure of input database
    sql = "select * from result limit 1"
    r0 = conn0.execute(sql).fetchone()
    input_columns = r0.keys()
    index_columns, data_columns = split_columns(input_columns)
    print data_columns
    assert ("ProcId" in index_columns)
    assert ("ThreadId" in index_columns)

    select = []
    group_by = []
    if on == "thread":
        new_index_columns = list(index_columns)
        new_index_columns.remove("ThreadId")
        group_by = map(quote, new_index_columns)
        select.extend(group_by)
        select.append("COUNT(ThreadId) AS ThreadCount")
        for k in data_columns:
            if k == "time":
                select.append("SUM(time) AS SumTime")
                select.append("MAX(time) AS time")
            elif k == "RDTSC":
                select.append("SUM(RDTSC) AS SumRDTSC")
                select.append("MAX(RDTSC) AS MaxRDTSC")
            elif k == "inverseClock":
                select.append("inverseClock")
            elif k == "CallCount":
                select.append("SUM(CallCount) AS SumCallCount")
            else:
                select.append("SUM(\"{0}\") AS \"{0}\"".format(k))
    else:
        new_index_columns = list(index_columns)
        new_index_columns.remove("ThreadId")
        new_index_columns.remove("ProcId")
        group_by = map(quote, new_index_columns)
        select.extend(group_by)
        select.append("COUNT(ProcId) AS ProcCount")
        select.append("COUNT(ThreadId) AS ThreadCount")
        for k in data_columns:
            if k == "time":
                select.append("SUM(time) AS SumTime")
                select.append("MAX(time) AS time")
            elif k == "RDTSC":
                select.append("SUM(RDTSC) AS SumRDTSC")
                select.append("MAX(RDTSC) AS MaxRDTSC")
            elif k == "inverseClock":
                select.append("inverseClock")
            elif k == "CallCount":
                select.append("SUM(CallCount) AS SumCallCount")
            else:
                select.append("SUM(\"{0}\") AS \"{0}\"".format(k))

    select = ", ".join(select)
    group_by = ", ".join(group_by)
    select_sql = "SELECT {0} FROM result GROUP BY {1}".format(
        select, group_by)

    # create result sqlite database
    r0 = conn0.execute(select_sql).fetchone()
    output_columns = list(r0.keys())
    output_types = [type(r0[k]) for k in output_columns]
    conn1 = sqlite3.connect(output_db)
    conn1.execute("DROP TABLE IF EXISTS result")
    type_pairs = zip(output_columns, output_types)
    sql = ["\"{0}\" {1}".format(k, SQLITE_TYPE[v]) for k, v in type_pairs]
    sql = "CREATE TABLE result (%s)" % ", ".join(sql)
    conn1.execute(sql)
    conn1.commit()

    for row in conn0.execute(select_sql).fetchall():
        ph_sql = ", ".join(["?"] * len(row))
        insert_row_sql = "INSERT INTO result VALUES ({0})".format(ph_sql)
        conn1.execute(insert_row_sql, row)
    conn1.commit()

    conn1.close()
    conn0.close()


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_db",
                        help="Input database for per-core values")
    parser.add_argument("output_db",
                        help="Output database for aggregated values")
    parser.add_argument("--on", default="thread",
                        choices=["thread", "proc_thread"],
                        help="Data aggregation (default: thread)")
    args = parser.parse_args()
    aggregate(**vars(args))


if __name__ == "__main__":
    main()
