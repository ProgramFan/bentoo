# coding: utf-8

import string
import subprocess
import os


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


def has_program(cmd):
    '''Check if a program exists in $PATH'''
    try:
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return True
    except OSError:
        return False
    except subprocess.CalledProcessError:
        return True


def shell_quote(var):
    '''Quote a string so it appears as a whole in bash commands'''
    var = str(var)
    if any(i in var for i in set("*?[]${}(); ")):
        return "\"%s\"" % var
    return var


def make_bash_script(prolog, envs, cmds, outfile):
    '''Make a bash script

    The produced bash script looks like:

        #!/bin/bash
        #
        #PBS -l xxx
        #...

        export ENV=value
        export ENV=value
        ...

        cmd arg
        cmd arg
        ...

    The first part is the `prolog`, the second part is the envs, the thirdpart
    is the cmds.

    Arguments:
        prolog: list of strings, each is a line without `#`
        envs: dictionary of (string, string) pairs, each is an env variable
        cmds: list of lists, each is a line of command
    '''

    content = []
    content.append("#!/bin/bash")
    content.append("#")
    if prolog:
        content.extend("#{}".format(x) for x in prolog)
        content.append("#")
    content.append("")
    if envs:
        for key, value in envs.items():
            content.append("export {0}={1}".format(key, shell_quote(value)))
        content.append("")
    assert isinstance(cmds, list)
    for cmd in cmds:
        content.append(" ".join(map(shell_quote, cmd)))
    open(outfile, "w").write("\n".join(content))
    os.chmod(outfile, 0o755)
