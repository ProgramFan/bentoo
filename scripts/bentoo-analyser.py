#!/usr/bin/env python2.7
#
'''Analyser - Test project result analyser

Analyser provides command line interface to extract and display test result
data collected by Collector. It provided options to filter result, to choose
display table fields and to pivot resultant table. It provides a simple and
intuitive syntax.

To use the analyser, one invokes bentoo-analyser.py with -m for matcher/filter,
-c for fields selection and -p for pivoting. For example, one can display how
all timers of algorithms scales w.r.t. number of nodes when using 1 threads per
process using the following command line:

    bentoo-analyser.py result.sqlite -m nthreads=1 \
        -m timer_name~algs::Numerical*,algs::Copy* \
        -c timer_name,nnodes,max,summed -p timer_name,nnodes

Analyser tries to provide a simple CLI interface of pandas for simple use
cases, namely tasks need to be done quick and often in command line. More
sphosticated analysis need to be done directly in python using pandas etc.
'''

import argparse
import fnmatch
import os
import re
import sqlite3


def parse_list(repr):
    return [x.strip() for x in repr.split(",") if x.strip()]


class PandasReader(object):
    @staticmethod
    def _make_equal_match_func(value):
        if isinstance(value, list):

            def match(x):
                return str(x) in value

            return match
        else:

            def match(x):
                return x == type(x)(value)

            return match

    @staticmethod
    def _make_glob_match_func(value):
        if isinstance(value, list):

            def match(x):
                for v in value:
                    if fnmatch.fnmatch(str(x), v):
                        return True
                return False

            return match
        else:

            def match(x):
                return fnmatch.fnmatch(str(x), value)

            return match

    @classmethod
    def _build_pandas_matchers(cls, matches):
        '''Create pandas DataFrame filter from spec

        'spec' is a list of matchers, each matcher defines a rule for a single
        column match. Currently supported matchers are:
        1. name=value: dataframe[name] == value
        2. name=value,value,...: dataframe[name].isin([value, value, ...])
        3. name~value: fnmatch.fnmatch(dataframe[name], value)
        4. name~value,value,...: fnmatch any value
        '''
        compiled_matcher = []
        for item in matches:
            m = re.match(r'^(\w+)\s*([=~])\s*(.*)$', item)
            assert m is not None
            name, op, value = m.groups()
            if "," in value:
                value = [x.strip() for x in value.split(",")]
            else:
                value = value.strip()
            if op == "~":
                matcher = cls._make_glob_match_func(value)
            else:
                matcher = cls._make_equal_match_func(value)
            compiled_matcher.append((name, matcher))
        return compiled_matcher

    def __init__(self, backend="sqlite"):
        self.backend = backend

    def read_frame(self, data_file, matches, columns, pivot, save):
        reader = self.backend
        if self.backend == "auto":
            ext = os.path.splitext(data_file)[1]
            if ext in (".xls", ".xlsx"):
                reader = "excel"
            elif ext in (".sqlite", ".sqlite3"):
                reader = "sqlite"
            else:
                raise RuntimeError("Can not guess type of '%s'" % data_file)

        if reader == "excel":
            data = pandas.read_excel(data_file, index=False)
        elif reader == "sqlite":
            conn = sqlite3.connect(data_file)
            data = pandas.read_sql("SELECT * FROM result", conn)
        else:
            raise RuntimeError("Unknown backend '%s'" % reader)

        pandas_matchers = self._build_pandas_matchers(matches)
        for name, matcher in pandas_matchers:
            data = data[data[name].map(matcher)]

        if columns:
            real_columns = []
            for c in columns:
                real_columns.extend(parse_list(c))
            data = data[real_columns]

        if pivot:
            pivot_fields = parse_list(pivot)
            assert len(pivot_fields) in (2, 3)
            data = data.pivot(*pivot_fields)

        print data.to_string()
        if save:
            data.to_csv(save, index=True)


def print_table(header, rows):
    '''Print csv table into markdown table'''
    for row in rows:
        assert len(header) == len(row)
    colalign = ['>'] * len(header)
    colwidth = [0] * len(header)
    for i, c in enumerate(header):
        colwidth[i] = max(colwidth[i], len(str(c)))
    for item in rows:
        for i, c in enumerate(item):
            colwidth[i] = max(colwidth[i], len(str(c)))
    fmt = ["{:%s%d}" % (a, w) for a, w in zip(colalign, colwidth)]
    fmt = " | ".join(fmt)
    fmt = "| " + fmt + " |"
    print fmt.format(*header)
    sep = ["-" * c for c in colwidth]
    for i, a in enumerate(colalign):
        if a == '<':
            sep[i] = ":" + sep[i] + '-'
        elif a == '^':
            sep[i] = ":" + sep[i] + ':'
        elif a == '>':
            sep[i] = "-" + sep[i] + ':'
        else:
            raise RuntimeError("Invalid align spec '%s'" % a)
    print "|" + "|".join(sep) + "|"
    for item in rows:
        printfmt.format(*item)


class SqliteReader(object):

    types = {
        None: "NULL",
        int: "INTEGER",
        long: "INTEGER",
        float: "REAL",
        str: "TEXT",
        unicode: "TEXT",
        buffer: "BLOB"
    }

    globops = {"fnmatchcase": "GLOB", "fnmatch": "GLOB", "regex": "REGEXP"}

    @classmethod
    def _build_where_clause(cls, column_types, matches, glob_syntax):
        if not matches:
            return ""

        assert glob_syntax in cls.globops

        def quote(name, value):
            assert name in column_types
            sqlite_type = cls.types[column_types[name]]
            if sqlite_type == "TEXT":
                return "'{0}'".format(value)
            elif sqlite_type == "BLOB":
                return "x'{0}'".format(value)
            elif sqlite_type == "NULL":
                return ""
            else:
                return value

        sql_segs = []
        for item in matches:
            m = re.match(r'^(\w+)\s*([=~])\s*(.*)$', item)
            assert m is not None
            name, op, value = m.groups()
            if name not in column_types:
                continue
            if "," in value:
                value = parse_list(value)
            else:
                value = value.strip()
            if op == "=":
                if isinstance(value, list):
                    value = map(lambda x: quote(name, x), value)
                    sql_seg = "{0} IN ({1})".format(name, ", ".join(value))
                else:
                    value = quote(name, value)
                    sql_seg = "{0} == {1}".format(name, value)
            else:
                assert cls.types[column_types[name]] == "TEXT"
                glob_op = cls.globops[glob_syntax]
                if isinstance(value, list):
                    quoted = [
                        "{0} {1} '{2}'".format(name, glob_op, x) for x in value
                    ]
                    sql_seg = "(" + " OR ".join(quoted) + ")"
                else:
                    sql_seg = "{0} {1} '{2}'".format(name, glob_op, value)
            sql_segs.append(sql_seg)
        return "WHERE %s" % " AND ".join(sql_segs)

    @classmethod
    def _build_select_clause(cls, column_types, columns):
        if not columns:
            return "*"
        real_columns = []
        for f in columns:
            real_columns.extend(parse_list(f))
        for f in real_columns:
            assert f in column_types
        return ", ".join(real_columns)

    def __init__(self, glob_syntax="fnmatch"):
        self.glob_syntax = glob_syntax

    def read_frame(self, data_file, matches, columns, pivot, save):
        conn = sqlite3.connect(data_file)
        if self.glob_syntax == "regex":
            conn.create_function("regexp", 2,
                                 lambda x, y: 1 if re.match(x, y) else 0)

        cur = conn.cursor()
        cur.execute("SELECT * FROM result ORDER BY ROWID ASC LIMIT 1")
        row = cur.fetchone()
        data_columns = [x[0] for x in cur.description]
        data_types = dict(zip(data_columns, [type(x) for x in row]))

        selects = self._build_select_clause(data_types, columns)
        filters = self._build_where_clause(data_types, matches,
                                           self.glob_syntax)
        sql = "SELECT {0} FROM result {1}".format(selects, filters)

        cur = conn.cursor()
        cur.execute(sql)
        for item in cur:
            data_rows.append(item)
        # TODO: We do not support pivot at the moment
        if False and pivot:
            pivot_fields = parse_list(pivot)
            assert len(pivot_fields) in (2, 3)
            data = data.pivot(*pivot_fields)

        print_table(data_columns, data_rows)
        if save:
            import csv
            # FIXME: change here
            data.to_csv(save, index=True)


def make_reader(reader, *args, **kwargs):
    if reader == "sqlite":
        return SqliteReader(glob_syntax=kwargs.get("sqlite_glob_syntax"))
    elif reader == "pandas":
        import pandas
        return PandasReader(backend=kwargs.get("pandas_backend"))
    else:
        raise RuntimeError("Unknown reader '%s'" % reader)


def analyse_data(data_file,
                 reader,
                 matches,
                 columns,
                 pivot=None,
                 save=None,
                 **kwargs):
    reader = make_reader(reader, **kwargs)
    reader.read_frame(data_file, matches, columns, pivot, save)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("data_file", help="Database file")
    parser.add_argument(
        "-r",
        "--reader",
        choices=["sqlite", "pandas"],
        default="pandas",
        help="Database reader (default: pandas)")
    parser.add_argument(
        "-m",
        "--matches",
        "--filter",
        action='append',
        default=[],
        help="Value filter, name[~=]value")
    parser.add_argument(
        "-c",
        "--columns",
        action='append',
        default=[],
        help="Columns to display, value or list of values")
    parser.add_argument(
        "-p",
        "--pivot",
        default=None,
        help="Pivoting fields, 2 or 3 element list")
    parser.add_argument("-s", "--save", help="Save result to a CSV file")

    ag = parser.add_argument_group("Sqlite Reader Options")
    ag.add_argument(
        "--sqlite-glob-syntax",
        choices=["fnmatch", "regex"],
        default="fnmatch",
        help="Globbing operator syntax (default: fnmatch)")

    ag = parser.add_argument_group("Pandas Reader Options")
    ag.add_argument(
        "--pandas-backend",
        choices=["excel", "sqlite3", "auto"],
        default="auto",
        help="Pandas IO backend (default: auto)")

    args = parser.parse_args()
    analyse_data(
        args.data_file,
        args.reader,
        args.matches,
        args.columns,
        args.pivot,
        args.save,
        sqlite_glob_syntax=args.sqlite_glob_syntax,
        pandas_backend=args.pandas_backend)


if __name__ == "__main__":
    main()
