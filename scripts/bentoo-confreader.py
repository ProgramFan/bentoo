#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#

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
    import sys
    dump(load(file(sys.argv[1])), file(sys.argv[2], "w"))
    print dumps(loads(file(sys.argv[1]).read()))


if __name__ == "__main__":
    main()
