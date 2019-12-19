#!/usr/bin/env python2.7
#

import bentoo.yaml
import re
from collections import OrderedDict


def load(fileobj, *args, **kwargs):
    return bentoo.yaml.load(fileobj,
                            Loader=bentoo.yaml.RoundTripLoader,
                            *args,
                            **kwargs)


def loads(string, *args, **kwargs):
    return bentoo.yaml.load(string,
                            Loader=bentoo.yaml.RoundTripLoader,
                            *args,
                            **kwargs)


def dump(data, fileobj, *args, **kwargs):
    fileobj.write(bentoo.yaml.dump(data), *args, **kwargs)


def dumps(data, *args, **kwargs):
    return bentoo.yaml.dump(data, *args, **kwargs)


def load_conf(fn):
    '''Load config file (in jsonc or yaml)

    This function parses a jsonc/yaml file. Unlike the builtin `json` module, it
    supports "//" like comments, uses 'str' for string representation and
    preserves the key orders.

    Args:
        fn (str): Name of the file to parse.

    Returns:
        OrderedDict: A dict representing the file content.

    '''
    def ununicodify(obj):
        result = None
        if isinstance(obj, OrderedDict):
            result = OrderedDict()
            for k, v in obj.iteritems():
                k1 = str(k) if isinstance(k, unicode) else k
                result[k1] = ununicodify(v)
        elif isinstance(obj, list):
            result = []
            for v in obj:
                result.append(ununicodify(v))
        elif isinstance(obj, unicode):
            result = str(obj)
        else:
            result = obj
        return result

    content = open(fn).read()
    content = re.sub(r"//.*$", "", content)
    return ununicodify(loads(content))
