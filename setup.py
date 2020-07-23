#!/usr/bin/env python
# coding: utf-8

from setuptools import find_packages, setup

setup(name="bentoo",
      description=
      "Benchmark Tools for Reproducible (Parallel) Performance Evaluation",
      version="0.25.3",
      packages=find_packages(exclude=("tests",)),
      entry_points={
          "console_scripts": [
              "bentoo-generator = bentoo.tools.generator:main",
              "bentoo-runner = bentoo.tools.runner:main",
              "bentoo-collector = bentoo.tools.collector:main",
              "bentoo-analyser = bentoo.tools.analyser:main",
              "bentoo-analyzer = bentoo.tools.analyser:main",
              "bentoo-aggregator = bentoo.tools.aggregator:main",
              "bentoo-metric = bentoo.tools.metric:main",
              "bentoo-quickstart = bentoo.tools.quickstart:main",
              "bentoo-calltree = bentoo.tools.calltree:main",
              "bentoo-merge = bentoo.tools.merge:main",
              "bentoo-calltree-analyser = bentoo.tools.calltree_analyser:main",
              "bentoo-viewer = bentoo.tools.viewer:main",
              "bentoo-svgconvert = bentoo.tools.svgconvert:main",
              "bentoo-confreader = bentoo.tools.confreader:main"
          ]
      },
      package_data={'': ['*.adoc', '*.rst', '*.md']},
      author="Yang Zhang",
      author_email="zyangmath@gmail.com",
      license="PSF",
      keywords="Benchmark;Performance Analysis",
      url="http://github.com/ProgramFan/bentoo")
