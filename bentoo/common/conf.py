# coding: utf-8

from __future__ import unicode_literals

import bentoo.yaml
import re
import json
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
    if fn.endswith(".json") or fn.endswith(".jsonc"):
        # json with "//" like line comments
        content = open(fn).read()
        content = re.sub(r"//.*$", "", content)
        return json.loads(content, object_pairs_hook=OrderedDict)
    elif fn.endswith(".yaml") or fn.endswith(".yml"):
        # yaml
        yaml = bentoo.yaml.YAML(pure=True)
        return yaml.load(fn)
    else:
        # default to regular json
        return json.load(fn, object_pairs_hook=OrderedDict)
