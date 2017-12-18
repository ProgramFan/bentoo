#!/usr/bin/env python
# coding: utf-8

from setuptools import setup, find_packages
setup(
    name="bentoo",
    description="Benchmarking tools",
    version="0.16.0",
    packages=find_packages(),
    scripts=["scripts/bentoo-generator.py", "scripts/bentoo-runner.py",
             "scripts/bentoo-collector.py", "scripts/bentoo-analyser.py",
             "scripts/bentoo-aggregator.py", "scripts/bentoo-metric.py",
             "scripts/bentoo-quickstart.py", "scripts/bentoo-calltree.py",
             "scripts/bentoo-merge.py", "scripts/bentoo-calltree-analyser.py",
             "scripts/bentoo-viewer.py", "scripts/bentoo-svgconvert.py",
             "scripts/bentoo-confreader.py"],
    package_data={
        '': ['*.adoc', '*.rst', '*.md']
    },
    author="Zhang YANG",
    author_email="zyangmath@gmail.com",
    license="PSF",
    keywords="Benchmark;Performance Analysis",
    url="http://github.com/ProgramFan/bentoo")
