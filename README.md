# bentoo: BENchmarking TOOls

bentoo is a set of tools to make reproducible research easy, focused specially
on performance evaluations and optimizations.

When doing research in performance evaluations and optimizations, one often
needs to generate test cases under different constraints, run these tests
(usually parallelly), extract performance data and do the analysis. One often
go back and forth among these stages to make the result firm. It creates a lot
of burden. For example, one usually develops several scripts to generate test
cases, run tests, collect interested data and do quick analysis. These scripts
are often not reusable, since they are bind to a special use case. So one
often has to develop a variant when the experiment changes, this pulls another
round of developing, testing and debugging.

bentoo tries to ease the above burden by providing a set of standards,
reusable components, and helping tools, for experiment design, test case
generation, test run, result collection and quick analysis. By using bentoo,
one no longer needs to write and debug similar (but different) scripts again
and again.  Instead, one focus on the experiments, describes it as required by
the standards, then use bentoo to generate test cases, run the tests in
different environments, gather the data and do quick analysis. Usually there
is no need to develop new scripts.

## Bentoo's abstraction of benchmarking pipeline

Bentoo relies on the essential abstraction of benchmarking, as four stages:

Design --> Prepare --> Run --> Collect --> Analysis

Design
: Design the experiment. Determine the test factors, test vectors and test
cases, as well as how the data would possibly support or dispute a
hyphothesis.

Prepare
: Prepare test cases. Generate binaries and model inputs, determine runtime
parameters such as procs, threads, environments. Create scripts to run these
cases.

Run
: Run test cases. Run test cases, until every case is finished successfully
and correctly.

Collect
: Collect interested data. Extract performance quantitles out of the test case
output. Organize these data in a meaningful manner. Store them for future
processing.

Analysis
: Analysis the dataset. Filter and transform the dataset. Check hyphothesis.
Plot curves.

The process does not follow linearly. One often need to go back to the design
after a quick analysis, when discovered a flaw in the experiment design. One
often need to check more data when doing analysis, then he goes back to
collect or even rerun (with a different of switch turned on).

## Bentoo's methodology to support the abstraction

bentoo's philosophy is to make everything explicit and to maximize
resuability. To be concrete, bentoo proposes the following interfaces:

A. Experiment Description Format;
B. Experiment Organization Format;
C. Experiment Data Storage Format;

And the following tools:
A. Generator: Transform experiment description to ready-to-run experiment
organization.
B. Runner: Read experiment organization, run each cases and preserve the
results.
C. Collector: Read finished experiments, extract performance data and save
them into user specified formats.
D. Analyser: Extract a data subset from saved data, show them in a meaningful
manner, to help analysis.

By the interfaces and tools, users can be freed from the tedious script
maintaining effort. One usually needs not to care about experiment
organization (although it helps). Runner and Collector understands the
experiment organization and do it for you. To be explicit, each tool generates
self-contained and descriptive output. For example, Generator would output a
directory containing test cases and their metadata. One can view the metadata
using any text editor and the content is easy to understand. The collected
data is also self contained so one can quickly grab their dataset. This type
of explicitly gives bentoo a unique power: users can do every stages in
different environments. One generate experiment input on the laptop with
generator, run experiments on super computers, collect the results just in
place, transfer them back and do analysis on their workstation.

To make it easier, bentoo is distributed as self-contained scripts. So there
is no need to install anything. Just copy the related scripts and start to
use.

## Using bentoo

Just following the help messages of individual tools.

