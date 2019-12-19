#!/usr/bin/env python2.7
#

from builtins import str
import string


def replace_template(template, varvalues):
    return string.Template(str(template)).safe_substitute(varvalues)


def safe_eval(expr):
    try:
        result = eval(str(expr))
    except ZeroDivisionError:
        result = 0
    except Exception:
        result = str(expr)
    return result
