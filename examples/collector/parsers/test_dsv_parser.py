#!/usr/bin/env python2.7
#

from bentoo_collector import DsvParser
import pprint

def main():
    parser = DsvParser([], {'sep': ','})
    for t in parser.itertables("csv.log"):
        print(t)

if __name__ == "__main__":
    main()
