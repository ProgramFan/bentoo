#!/usr/bin/env python2.7
#

from bentoo_collector import PipetableParser
import pprint

def main():
    parser = PipetableParser([], {})
    for t in parser.itertables("pipetable.log"):
        print(t)

if __name__ == "__main__":
    main()
