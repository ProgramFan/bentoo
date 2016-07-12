#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#

'''
bentoo-confreader - Read and convert config files

This module reads input files and convert them to json or yaml format. It reads
both yaml and json files and write to yaml file if pyyaml is installed.
Otherwise, only json to json is supported.
'''

import argparse
import collections

try:
    import yaml

    def dict_representer(dumper, data):
        return dumper.represent_dict(data.iteritems())

    def dict_constructor(loader, node):
        return collections.OrderedDict(loader.construct_pairs(node))

    yaml.add_representer(collections.OrderedDict, dict_representer)
    yaml.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                         dict_constructor)

    def load(fileobj, *args, **kwargs):
        return yaml.load(fileobj, *args, **kwargs)

    def loads(string, *args, **kwargs):
        return yaml.load(string, *args, **kwargs)

    def dump(data, fileobj, *args, **kwargs):
        fileobj.write(yaml.dump(data), *args, **kwargs)

    def dumps(data, *args, **kwargs):
        return yaml.dump(data, *args, **kwargs)

except ImportError:
    import json

    def load(fileobj, *args, **kwargs):
        return json.load(fileobj,
                         object_pairs_hook=collections.OrderedDict,
                         *args,
                         **kwargs)

    def loads(string, *args, **kwargs):
        return json.loads(string,
                          object_pairs_hook=collections.OrderedDict,
                          *args,
                          **kwargs)

    def dump(data, fileobj, *args, **kwargs):
        kwargs["indent"] = 2
        json.dump(data, fileobj, *args, **kwargs)

    def dumps(data, *args, **kwargs):
        kwargs["indent"] = 2
        return json.dumps(data, *args, **kwargs)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("src_file", help="Source file to convert")
    parser.add_argument("dst_file", help="Dest file to write to")

    args = parser.parse_args()
    dump(load(file(args.src_file)), file(args.dst_file, "w"))


if __name__ == "__main__":
    main()
