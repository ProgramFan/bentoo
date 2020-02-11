#!/usr/bin/env python2.7
#

from bentoo_collector import YamlParser
import pprint

def main():
    parser = YamlParser([], {})
    for t in parser.itertables("yaml.log"):
        print(t)

if __name__ == "__main__":
    main()
