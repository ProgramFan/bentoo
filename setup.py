#!/usr/bin/env python
# coding: utf-8

from setuptools import setup, find_packages
setup(
    name="bentoo",
    description="Benchmarking tools",
    version="0.10-dev",
    packages=find_packages(),
    scripts=["scripts/generator.py", "scripts/runner.py",
             "scripts/collector.py", "scripts/analyser.py",
             "scripts/bentoo-quickstart.py"],
    package_data={
        '': ['*.adoc', '*.rst', '*.md']
    },
    author="Zhang YANG",
    author_email="zyangmath@gmail.com",
    license="PSF",
    keywords="Benchmark;Performance Analysis",
    url="http://github.com/ProgramFan/bentoo"
)
