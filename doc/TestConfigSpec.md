# Test Project Specification

## Terminology

**Test case**: A specific run of a specific executable under specific
environments. Test case shall produce the same results when running under the
same hardware/software environments. It's the minimal unit in a test project.

**Test project**: A collection of test cases, usually organized in a specific
way to facilitate analysis.

## Organization

### Basic organization

A test project is organized as a hierarchy of directories, each directory
contains a specification file `TestConfig.json` which specifies the content of
the directory. The directory hierarchy shall be a complete tree, i.e., each leaf
directory shall be on the same level in the hierarchy. for example:

```
user@localhost # tree .
.
|-- auto.1p
|   |-- 1
|   |   `-- TestConfig.json
|   |-- 2
|   |   `-- TestConfig.json
|   |-- 4
|   |   `-- TestConfig.json
|   `-- TestConfig.json
|-- fixed.16p
|   |-- 1
|   |   `-- TestConfig.json
|   |-- 2
|   |   `-- TestConfig.json
|   |-- 4
|   |   `-- TestConfig.json
|   `-- TestConfig.json
|-- fixed.2p
|   |-- 1
|   |   `-- TestConfig.json
|   |-- 2
|   |   `-- TestConfig.json
|   |-- 4
|   |   `-- TestConfig.json
|   `-- TestConfig.json
`-- TestConfig.json
```

The top level directory corresponds to a test project and the project
information is specified in its `TestConfig.json` as the following:
```json
{
    "project": {
        "name": "MyAwesomeTestProject",
        "comment": "This is an awesome project, owned by me!!",
        "dimensions": ["model", "nnodes"]
    }
}
```

The `dimensions` field is crucial. It names each level of the directory. For
example, in the above example, the first level is 'model', the second level is
'nnodes', and each test case is indexed by (model, nnodes).

Intermediate directories corresponds to test levels, they are named according to
`dimensions` field in project information and the name of the directory
corresponds to the value for a specific case. It contains sublevel specification
as the following:
```json
{
    "sub_directories": ["1", "2", "4"]
}
```
or
```json
{
    "sub_directories": {
        "dimension": "nnodes",
        "directories": ["1", "2", "4"]
    }
}
```
The latter is provided to be self-document and the `dimension` field shall be
the same value according to the level of the subdirectories as specified in
project information.

Note that the top level directory is also an intermediate directory and shall
contains the same `sub_directory` specification.

Each leaf directory corresponds to a test case, whose detail is specified in its
`TestConfig.json` file:
```json
{
    "test_case": {
        "cmd": ["${project_root}/${app}/bin/main2d", "linadv-2d.input"],
        "envs": {
            "OMP_NUM_THREADS": "1"
        },
        "run": {
            "nnodes": 1,
            "procs_per_node": 1,
            "tasks_per_proc": 1,
            "nprocs": 1
        },
        "results": ["LinAdvSL-linadv_2d.log"]
    }
}
```

The `cmd`, `run` and `results` fields are mandatory and `envs` is optional.
`cmd` is a list denoting the command and argument to run the case. `envs`
contains environment variables to override. `run` contains parallel run
configuration and the information is passed directly to platform-specific
backends. `results` contains a list of files for results, one can use `STDOUT`
as a special file.

Test case can be viewed as running in the test case directory and every relative
path in the test case specification as well as in the test itself is relative to
the test case directory. **This is important**.

Every path in the test case specification can contain the following predefined
template variables, which will be substituted to appropriate values afterwards:
`project_root` and dimension names specificed in project information.
`project_root` is the absolute path of top level directory and each dimension
name contains the name of corresponding  intermediate directory of the test
case.

### Advanced features

Writting `TestConfig.json` for every single test case can be tedious and
error-prone. Even more work is involved if you want changed the directory
structure, to add one level of intermediate directory for example. To solve this
problem, At any intermediate directory level, a test matrix can be used to
generate remaining sub-directories as well as final test cases.

Test matrix denotes a cartetian product of different test factors. For example,
we want to test an algorithm with variable models and nnodes, where:
```python
models = ["auto.1p", "fixed.2p", "fixed.16p"]
nnodes = [1, 2, 4, 8, 16, 32]
```
The the test matrix contains all cases from `itertools.product(models, nnodes)`.
It saves us from manually making sub-directories and writting `TestConfig.json`
for test cases.

Test matrix is specified as the following:
```json
{
    "test_matrix": {
        "dimensions": {
            "names": ["model", "nnodes"],
            "values": {
                "model": ["auto.1p", "fixed.2p", "fixed.16p"],
                "nnodes": [1, 2, 4, 8, 16, 32]
            }
        },
        "test_case_generator": "GENERATOR_NAME",
        "GENERATOR_SPECIFIC_FIELDS": {
            "KEY": "VALUE"
        }
    }
}
```

`dimensions` fields specifies the directory levels as well as sub-directory
names of possible test cases. We use `names` and `values` fields because we want
the tests to be ordered since json does not maintain the order of object keys.

`test_case_generator` specifies the test case generator name, which is then used
to generate test case config as specified in test case specification. Generator
shall be provided generator-specific config, which is generator-dependent.
Currently supported generators are "template" and "custom".

`template` generator simply do template substitution over each case. It requires
the `template` field in `test_matrix`:
```json
{
    "test_matrix": {
        "test_case_generator": "template",
        "template": {
            "cmd": ["${project_root}/bin/main2d",
                    "${project_root}/input/linadv2d.input.${model}.${nnode}"],
            "envs": {
                "OMP_NUM_THREADS": 1
            },
            "run": {
                "nnodes": "${nnodes}",
                "procs_per_node": 12,
                "tasks_per_proc": 1,
                "nprocs": "${nnodes} * 12"
            },
            "results": ["LinAdvSL-linadv_2d.log"]
        }
    }
}
```
`template` field has the same format as test case specification, it uses the
same set of template variables. Moreover, it supports simple arithmetic in field
values, for example `${nnodes} * 12`. template is firstly substituted and then
evaluated and the resultant map is the test case.

Template generator is enough for many cases, but some tests depends on dimension
values in a complicated way, which can not be supported by template substitution
and simple arithmetic. To accommodate this case, custom generator is supported,
where users define their own generator.

Custom generator calls user-defined functions over each case to generate test
cases. It requires the `custom_generator` field in `test_matrix`:
```json
{
    "test_matrix": {
        "test_case_generator": "custom",
        "custom_generator": {
            "import": "make_case.py",
            "func": "make_case",
            "args": {
                "bin_name": "main2d.lite"
            }
        }
    }
}
```

Currently only python is supported as the generator customization language.
`import` denotes the python script file containing the generator function,
`func` is the global function name in the script to be used for case generation.
The function shall accepts the following predefined arguments and extra
arguments are specified as keyword arguments in `args` field:
```python
# Arguments:
#   project_root - String for the absolute path of the project top level dir
#      cfg_vpath - OrderedDict for intermediate sub-directory of the TestConfig
#                  file, as [(dim_name, dim_value), ...]
#     case_vpath - OrderedDict for intermediate sub-directory of the test case
#                  w.r.t. the TestConfig file, as [(dim_name, dim_value), ...]
#
# Returns:
#   A dictionary containing "cmd", "envs", "run" and "results" fields, the same
#   as test case specification, except that no template substitution nor simple
#   arithmetic.
def make_case(project_root, cfg_vpath, case_vpath, **kwargs):
    # generate case spec w.r.t. the arguments
    return {}
```

The `import` path can be relative path or absolute path, it can also contains
template variables as supported by test case specification. If relative path is
used, it is relative to the `TestConfig.json` importing the script. The python
script can use any python modules as long as it exists. It's evaluated in a
separate name space so no name space pollution is possible. It's just python.

## Processing

The project information is feed into a parser, which generate an working
directory resembling the same structure as the project, except that all
generators are invoked and only the results are left.
