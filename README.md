# Bentoo: A Performance Experiment Tool for Reproducible Performance Optimization Research

## Why bentoo

**bentoo** is a set of tools to make reproducible performance optimization research easy.

Performance optimization research involves a variety of activities. One need to design algorithms, define confirming experiments, run these experiments, collect performance results and do solid (possibly statistical) analysis. These activities are usually done iteratively and one often goes back and forth among these steps. This involves a lot of efforts in designing and debugging automating scripts. These scripts are often bind to a specific experiments and not easily reusable, causing a lot of headache for everyday research.

bentoo tries to ease this burden by providing a set of interfaces, reusable components, and helpful tools, for defining and running performance experiments, as well as data extraction and analysis. With bentoo, one only needs to focus on experiments design and hypothesis validation. Painful scripts design and debugging becomes the past.

bentoo tries to ease this burden by providing a set of interfaces, reusable components, and helpful tools, for defining and running performance experiments, as well as data extraction and analysis. With bentoo, one only needs to focus on experiments design and hypothesis validation. Painful scripts design and debugging becomes the past.

## Bentoo's Performance Experiments Strategy

Bentoo abstracts performance experiments as the following five-stage pipeline:

```
Design --> Prepare --> Run --> Collect --> Analysis
  ^                                         |
  |-----------------------------------------|
```

**Design**: Design the experiment. Determine the test factors, test vectors and test cases, as well as how the data would possibly support or dispute a hypothesis.

**Prepare**: Prepare test cases. Generate binaries and model inputs, determine runtime parameters such as processes, threads, environments. Create test cases with these ingredients.

**Run**: Run test cases. Run test cases, until every case is finished successfully and correctly.

**Collect**: Collect all interesting data. Collect all performance data and store them for further processing.

**Analysis**: Do solid analysis based on collected data.

One need to go back and forth between `prepare`, `run`, `collect` and `analysis`, until the data is reproducible and outliers are eliminated.

## Bentoo's Component-based Design

Bentoo consists of the following components, each is an standalone tool:

- **Generator**: Transform experiment description to ready-to-run experiment organization.
- **Runner**: Read experiment organization, run each cases and preserve the results.
- **Collector**: Read finished experiments, extract performance data and save them into user specified formats.
- **Analyser**: Extract a data subset from saved data, show them in a meaningful manner, to help analysis.

## Using bentoo

Just following the help messages of individual tools.
