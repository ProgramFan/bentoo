# New Design

## Core concepts

We seperate the test into 4 stages: "test generation", "test run", "data
collect", and "data analysis".

---
Test Specification --> |Generator| --> -Test Suite Tree- --> |Runner| -->
-Test Result Tree- |Collector| --> -Data Package- --> |Analyser| -->
-Reduced/Transformed Dataset, Virtualizations, etc-
---

To easy the run and rerun process, we merge the Test Suite Tree and Test
Result Tree. So they share the same structure and the same contents. This
makes the tree have states: clean, run. For a clean tree, there are no
results. For a run tree, there are partial results. As long as the tree has
results, it can be feed into the collector to extract data.

### Test Spec

We abandon the previous file tree based test spec, which is too verbose and
too complicated for most usage, yet not consistant with other file tree base
spec such as cmake. Let's explain it in more detail. The test organization
concept is organize collections of test cases in a structured manner, so
performances analysis can be carried out easily and smoothly. Since any
performance analysis involved comparision of values in different cases and the
compared cases shall only differ in one variable. That is to say, all other
variables in the tests shall have the same structure. For example, if we want
to analyse the strong scalability, only the nprocs changed, the model, the
binary (algorithm strategy) shall be the same. So it makes no sense to compare
n6-m1 with n18-(unknown model). This means arbitrary tree is not necessary for
performance analysis. On the other hand, a full tree is a better
representation. In a full tree, each intermediate node represents a set of
test cases or a set of test suites. Node on the same level shares the same
variable name, differs only in values. And we want to make clear here for any
incomplete tree, it can be extended to a full tree by adding intermediate
nodes, that is, assigning default variable values to the missing attributes.
So it makes no sense to use abitrary tree. A full tree is sufficient.

A full tree is much simpler to express. In the previous spec, we want to
support different combinations. That is to say, we allow the user to specify
parts of the case using detailed spec, while leave other parts with
automatically generation, to combine the goodness of both approaches. It turns
out seldom used. Most of the time, users want to provide a custom
specificatoin for their cases, to get through the complications of input
preparation. While the test case structure is always simple cart product of
value combinations. This inverts our spec design priority. Now we understand
that we shall provide a easy (yet complete) way to specify case structure, and
make it fully customizable to generate each case (yet simplify the interface,
since it's often used).

So the decision is that we drop the property that a test suite tree is a valid
test spec. It's simply not necessary. So we do not have be compatible with its
structure. The test suite tree can use its current structure, but we want a
new test spec.

The key concepts in the new spec is "case collection" and "case generator".
"Case collection" is a table of cases, each case is a row in the table. The
columns of the table represents the test variables. Each case has a unique
vector of test variable values. That is:

case_id | model | nnodes | nimcs | test_id
0 | Planewave | 1 | 0 | 0
0 | Planewave | 1 | 0 | 0
0 | Planewave | 1 | 0 | 0
0 | Planewave | 1 | 0 | 0
0 | Planewave | 1 | 0 | 0
0 | Planewave | 1 | 0 | 0

So you see the structure, its simple and straight forward.

"Case generator" is a callback defining how to prepare for each case. It
generate necessary files and a mandotary test-case-spec json file containing
necessary information to run the case and define the results. for example:

```python
def make_case(conf_root, dest_root, case_vpath, **kwargs):
    pass
```
