#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
'''bentoo-metric - Calculate performance metrics

This tool calculates predefined performance metrics using raw performance data.
The input is a database containing row performance data, the output is a
database containing only computed metrics (have the same structure as the input
database).

Users can supply their own metrics using json or yaml file. For likwid metric
groups, just specify the architecture and the groupname, or specify directly
the groupfile.

User defined metrics example:

    {
        "data": ["ProcCount", "SumRDTSC", "MaxRDTSC"],
        "metrics": [
            {"name": "Load Balance Efficiency",
             "type": "float",
             "formula": "SumRDTSC / (MaxRDTSC * ProcCount)"}
        ]
    }

'''

from builtins import zip
from builtins import str
from builtins import map
import os
import re
import argparse
import sqlite3

try:
    import yaml

    def load(fileobj, *args, **kwargs):
        return yaml.safe_load(fileobj, *args, **kwargs)

    def loads(string, *args, **kwargs):
        return yaml.safe_load(string, *args, **kwargs)

except ImportError:
    import json

    def load(fileobj, *args, **kwargs):
        return json.load(
            fileobj,
            object_pairs_hook=collections.OrderedDict,
            *args,
            **kwargs)

    def loads(string, *args, **kwargs):
        return json.loads(
            string, object_pairs_hook=collections.OrderedDict, *args, **kwargs)


SQLITE_TYPE = {
    type(None): "NULL",
    int: "INTEGER",
    int: "INTEGER",
    float: "REAL",
    str: "TEXT",
    str: "TEXT",
    buffer: "BLOB"
}


def split_columns(columns):
    '''split 'columns' into (index_columns, data_columns)'''
    timer_column_index = columns.index("TimerName")
    return (columns[:timer_column_index + 1], columns[timer_column_index + 1:])


def eval_formula(formula, values):
    try:
        result = eval(formula, values)
    except:
        result = 0
    return result


def quote(x):
    return "\"{}\"".format(x)


def tokenize(x):
    return re.sub(r"[^a-zA-Z0-9_]", "_", x)


def compute_metrics(input_db, output_db, spec):
    # Open input database
    conn0 = sqlite3.connect(input_db)
    conn0.row_factory = sqlite3.Row

    # Discover the structure of input database and define output database
    # structure.
    sql = "select * from result limit 1"
    r0 = conn0.execute(sql).fetchone()
    input_columns = list(r0.keys())
    index_columns, data_columns = split_columns(input_columns)
    output_columns = list(index_columns)
    output_columns.extend(tokenize(x["name"]) for x in spec["metrics"])
    output_types = [type(r0[x]) for x in index_columns]
    output_types.extend(x["type"] for x in spec["metrics"])

    # Create output database
    conn1 = sqlite3.connect(output_db)
    conn1.execute("DROP TABLE IF EXISTS result")
    type_pairs = list(zip(output_columns, output_types))
    sql = ["\"{0}\" {1}".format(k, SQLITE_TYPE[v]) for k, v in type_pairs]
    sql = "CREATE TABLE result (%s)" % ", ".join(sql)
    conn1.execute(sql)
    conn1.commit()

    def compute_one_row(row):
        var_values = dict(row)
        for item in spec["data"]:
            if isinstance(item, list):
                k, v = list(map(str, item))
                var_values[v] = row[k]
        result = [row[k] for k in index_columns]
        for item in spec["metrics"]:
            value = eval_formula(item["formula"], var_values)
            result.append(value)
        return result

    select = list(map(quote, input_columns))
    select = ", ".join(select)
    order_by = list(map(quote, index_columns))
    order_by = ", ".join(order_by)
    select_sql = "SELECT {0} FROM result ORDER BY {1}".format(select, order_by)
    data = conn0.execute(select_sql)
    for row in data.fetchall():
        row_values = compute_one_row(row)
        ph_sql = ", ".join(["?"] * len(row_values))
        insert_row_sql = "INSERT INTO result VALUES ({0})".format(ph_sql)
        conn1.execute(insert_row_sql, row_values)
    conn1.commit()

    conn1.close()
    conn0.close()


def locate_likwid_groupfile(arch, group):
    # NOTE: Here we respect Likwid's group file locating mechanism: first try
    # "~/.likwid/groups/ARCH/GROUP", then "LIKWID_HOME/share/likwid
    # /perfgroups/ARCH/GROUP".
    user_conf_path = os.path.expanduser("~/.likwid/groups")
    group_file = os.path.join(user_conf_path, arch, group + ".txt")
    if os.path.exists(group_file):
        return group_file
    sys_path = os.environ["PATH"].split(":")
    for p in sys_path:
        if os.path.exists(os.path.join(p, "likwid-perfctr")):
            likwid_home = os.path.dirname(os.path.abspath(p))
            group_file = os.path.join(likwid_home, "share", "likwid",
                                      "perfgroups", arch, group + ".txt")
            if not os.path.exists(group_file):
                raise ValueError("Bad likwid installation: can not find "
                                 "'%s' for '%s' in '%s'" % (group, arch,
                                                            likwid_home))
            return group_file
    raise ValueError("Can not find likwid group '%s' for '%s'" % (group, arch))


def parse_likwid_metrics(group_file):
    match = re.search(r"EVENTSET\n(.*?)\n\nMETRICS\n(.*?)\n\n",
                      file(group_file).read(), re.S)
    assert match
    data = ["time", "inverseClock"]
    for eventstr in match.group(1).split("\n"):
        counter, event = eventstr.split()
        data.append(["{}:{}".format(event, counter), counter])
    metrics = []
    for metricstr in match.group(2).split("\n"):
        segs = metricstr.split()
        formula = segs[-1]
        name = segs[:-1]
        if re.match(r"\[.+\]", name[-1]):
            name = name[:-1]
        name = " ".join(name)
        f = {"name": name, "type": float, "formula": formula}
        metrics.append(f)
    return {"data": data, "metrics": metrics}


def parse_user_metrics(metric_file):
    content = load(file(metric_file))
    spec = {"data": content["data"], "metrics": []}
    spec["data"] = content["data"]
    for item in content["metrics"]:
        f = {"name": item["name"],
             "type": eval(item["type"], {}),
             "formula": str(item["formula"])}
        spec["metrics"].append(f)
    return spec


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_db", help="Input database with raw data")
    parser.add_argument("output_db", help="Output Database for metrics")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--likwid-archgroup",
        default=None,
        help="Likwid arch and group name (ARCH:GROUP)")
    group.add_argument(
        "--likwid-groupfile", default=None, help="Likwid perfgroup file")
    group.add_argument(
        "--user-metrics",
        default=None,
        help="User defined metrics (json or yaml)")

    args = parser.parse_args()
    if args.likwid_archgroup:
        arch, group = args.likwid_archgroup.split(":")
        likwid_groupfile = locate_likwid_groupfile(arch, group)
        metrics = parse_likwid_metrics(likwid_groupfile)
    elif args.likwid_groupfile:
        metrics = parse_likwid_metrics(args.likwid_groupfile)
    elif args.user_metrics:
        metrics = parse_user_metrics(args.user_metrics)
    else:
        raise ValueError("No metrics is supplied")

    compute_metrics(args.input_db, args.output_db, metrics)


if __name__ == "__main__":
    main()
