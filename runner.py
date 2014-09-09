#!/usr/bin/env python2.7
#

import os
import sys
import argparse


def main():
    parser = argparse.ArgumentParser()

    ag = parser.add_argument_group("Global options")
    ag.add_argument("project-dir",
                    help="Directory of the test project")
    ag.add_argument("--result-dir",
                    help="Directory for test results")

    ag = parser.add_argument_group("Testcase filter options")
    ag.add_argument("--except",
                    help="Test cases to exclude, support wildcards")
    ag.add_argument("--only",
                    help="Test cases to include, support wildcards")

    ag = parser.add_argument_group("Testcase runner options")
    ag.add_argument("--case-runner",
                    help="Runner to choose, can be mpirun and yhrun")
    ag.add_argument("--timeout",
                    help="Timeout for each case, in minites")

    config = parser.parse_args()
    print config

if __name__ == "__main__":
    main()
