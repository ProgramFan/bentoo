# Bentoo 简明教程

[Bentoo](https://github.com/ProgramFan/bentoo) 是一套结构化性能测试工具，适用于并行算法、性能优化等研究中的性能测试。其特性包括：

1. 确保测试可重复
2. 自动抽取并归档测试结果
3. 适配天河、神威、曙光等多种超级计算机作业调度系统
4. 基本功能只依赖于 Python 标准库

本文对 Bentoo 的使用方法进行简单介绍。

[TOC]

## 性能测试基本流程

```flow
st=>start: 开始
def=>operation: 定义测试用例
work=>operation: 生成工作目录
run=>operation: 运行测试用例
collect=>operation: 收集性能数据
analysis=>operation: 分析性能数据
e=>end: 完成

st->def(right)->work(right)->run(right)->collect(right)->analysis->e
```

Bentoo 通过一系列工具，支持上述工作流程：

1. **bentoo-quickstart**: 快速定义测试用例
2. **bentoo-generator**: 自动生成工作目录
3. **bentoo-runner**: 自动运行测试用例，重新运行未完成用例
4. **bentoo-collector**: 自动解析性能数据并归档为 sqlite 数据库
5. **bentoo-analyzer**: 简单分析性能数据

## 结构化性能测试

Bentoo 的核心是结构化性能测试。结构化性能测试将性能测试定义为$N$个影响因素构成的$N$维测试空间。例如：对程序 `Euler` 进行强扩展性测试，研究其在纯进程并行与多线程并行下面的性能和扩展性对比，并确保性能数据在统计意义下的有效性。那么影响因素包括：

1. 并行模式 (mode)：包括纯进程并行 (mpi-core)、结点内纯线程并行 (mpi-node)、处理器内纯线程并行 (mpi-socket) 三种
2. 结点数 (nnodes)：计算结点数目或总核心数，从1到128结点，每结点2块8核处理器，强扩展用结点数倍增方式
3. 测试 ID (test_id)：同一设定的多次测试的测试编号，测试5次，取值为0-4

上述用例的所有影响因素按笛卡尔积的方式构成一个三维的测试空间：$[\text{mpi-core}, \text{mpi-node}, \text{mpi-socket}] \times [1, 2, 4, 8, 16, 32, 64, 128] \times [0, 1, 2 ,3, 4]$，包括 120 个测试向量，对应 120 个测试用例。

在 Bentoo 中，**影响因素称为 “test factor”，测试向量称为 “test vector” ，测试用例称为 “test case”**。

## 定义测试用例

Bentoo 将一次结构化性能测试定义为 **“测试工程 （test project)”**。测试工程是一个包括 `TestProjectConfig.json` 文件的目录。一个典型的测试工程如下：

```
Euler
|-- bin
|   \-- main3d
|-- data
|   \-- Model.stl
|-- templates
|   \-- 3d.input.template
|-- TestProjectConfig.json
\-- make-case.py
```

`TestProjectConfig.json` 是一个 [json](https://json.org) 或 [yaml](https://yaml.org) 格式的数据文件，定义了测试工程的影响因素、测试向量、测试用例等描述信息。`make-case.py` 是用 python 编写的测试向量和测试用例生成器，使用 `3d.input.template` 等辅助文件，在指定的测试用例目录中生成独立运行该测试用例所需的全部文件，并向 Bentoo 返回测试用例的运行环境要求。`bin` 通常用于放置可执行文件，`data` 通常用于放置大型数据文件。

### TestProjectConfig.json

上述 Euler 测试对应的 `TestProjectConfig.json` 如下：

```json
{
  "version": 1,
  "project": {
    "name": "Euler",
    "description": "Euler strong scaling study w.r.t. proc-thread combinations",
    "test_factors": ["mode", "nnodes", "test_id"],
    "test_vector_generator": "custom",
    "test_case_generator": "custom",
    "data_files": ["bin", "data"]
  },
  "custom_vector_generator": {
    "import": "make_case.py",
    "func": "make_vectors",
    "args": {}
  },
  "custom_case_generator": {
    "import": "make_case.py",
    "func": "make_case",
    "args": {}
  }
}
```

上述文件包括三个关键字段：`project`、`custom_vector_generator`、和`custom_case_generator`，`version` 选择当前测试工程定义文件的版本。

`project` 定义测试工程的基本结构，包括：名称 `name`、说明 `description`、影响因素 `test_factors`、测试向量生成器 `test_vector_generator`、测试用例生成器 `test_case_generator` 和辅助文件列表 `data_files`。其类型与取值如下：

- `name`: 字符串，测试工程名称
- `description`: 字符串，测试工程描述
- `test_factors`: 字符串列表，影响因素名称
- `test_vector_generator`: 字符串，测试向量生成器的类型，为 `simple`、`cart_product` 或`custom`
- `test_case_generator`: 字符串，测试用例生成器类型，为 `template` 或 `custom`
- `data_files`: 字符串列表，辅助文件或目录路径列表，每一项为一个绝对路径或相对路径，相对路径代表相对于 `TestProjectConfig.json` 所在的目录的路径。

`<TYPE>_vector_generator` 为与 `test_vector_generator` 匹配的测试向量生成器定义，`<TYPE>` 与 `test_vector_generator` 取值一致。

`<TYPE>_case_generator` 为与 `test_case_generator` 匹配的测试用例生成器定义，`<TYPE>` 与 `test_case_generator` 取值一致。

### 自定义测试向量生成器

`custom` 类型是最灵活的测试向量生成器类型。它执行一个 python 函数，接收其返回值作为测试向量定义。其在`TestProjectConfig.json` 中定义为一个字典，字典项固定为：

- `import`: 字符串，python 函数所在的文件，将通过 `import` 载入
- `func`: 字符串，待执行的函数名，必须为 `import` 所指定文件中的函数
- `args`: 字典，表示传递给 `func` 的 **额外参数**, 将通过 `**kwargs` 传递给 `func`

测试向量生成器所执行的函数原型为：

```python
def make_vectors(conf_root, test_factors, **kwargs):
  	result = []
  	# fill result with vectors of the same size as `test_factors`
  	return result
```

`conf_root` 为用 **绝对路径** 表示的测试工程路径，`test_factors` 为 `project` 字段定义的 `test_factors` 列表，`kwargs` 为在 `custom_vector_generator` 中定义的额外参数。

上述 `Euler` 示例的测试向量生成器函数为：

```python
import itertools

def make_vectors(conf_root, test_factors, **kwargs):
  	assert test_factors == ["mode", "nnodes", "test_id"]
  	mode = ["mpi-core", "mpi-socket", "mpi-node"]
  	nnodes = [1, 2, 4, 8 ,16, 32, 64, 128]
  	test_id = range(5)
  	return list(itertools.product(mode, nnodes, test_id))
```

### 自定义测试用例生成器

`custom` 类型是最灵活的测试用例生成器类型，也是最为常用的测试用例生成器类型。它执行一个 python 函数，接收其返回值作为测试用例定义，并由该函数准备测试用例的工作目录。其在`TestProjectConfig.json` 中定义为一个字典，字典项固定为：

- `import`: 字符串，python 函数所在的文件，将通过 `import` 载入
- `func`: 字符串，待执行的函数名，必须为 `import` 所指定文件中的函数
- `args`: 字典，表示传递给 `func` 的 **额外参数**, 将通过 `**kwargs` 传递给 `func`

测试用例生成器所执行的函数原型为：

```python
def make_case(conf_root, output_root, case_path, test_vector, **kwargs):
  	# expand test_vector
  	# prepare case asserts in `case_path`
  	# define test spec
  	cmd = []
  	envs = {}
  	run = {}
  	results = []
  	validator = {}
  	# calculate test spec and return
  	return collections.OrderedDict(zip(["cmd", "envs", "run", "results", "validator"],
    	                                 [cmd, envs, run, results, validator]))
```

`conf_root` 和 `output_root` 为用 **绝对路径** 表示的测试工程路径和工作目录路径，`case_path` 为用 **绝对路径** 表示的测试用例工作目录，`test_vector` 为测试用例所对应的测试向量，用 `OrdredDict` 表示。`kwargs` 为在 `custom_case_generator` 中定义的额外参数。

测试用例生成函数需要完成如下约定功能：

1. 在 `case_path` 中生成测试用例 `test_vector` 对应的辅助文件，包括输入文件、数据文件等
2. 向 Bentoo 返回测试用例的 **执行描述** ，即执行方法的详细描述

执行描述为一个 Python 字典，包括五个字段：

1. `cmd`：字符串列表，表示串行执行用例所执行的命令，如 `["./main3d", "3d.input"]` 等
2. `envs`: 字典（以字符串为键，任意类型为值），表示待设置的环境变量
3. `run`: 由指定键构成的字典，表示执行测试用例的资源需求和分配方法。键值的类型和定义为：
   1. `nnodes`: 整数，表示执行该测试用例所需计算结点数目
   2. `procs_per_node`: 整数，表示执行该测试用例时每个结点的进程数目
   3. `tasks_per_proc`: 整数，表示执行该测试用例时每个进程的线程数目
   4. `nprocs`: 整数，表示执行该测试用例所需的总进程数目
4. `results`: 字符串列表，表示测试用例输出结果文件，*必须为相对于 `case_path` 的相对路径*，标准输出和标准错误通过 `STDOUT` 和 `STDERR` 表示
5. `validator`: *可选*，由指定键构成的字典，表示检测测试用例是否成功完成的方法。键值的类型和定义为：
   1. `exists`: 字符串列表，表示检测指定的文件是否存在，*必须为相对于 `case_path` 的相对路径*。仅当所有文件均存在才返回真值
   2. `contains`: 以字符串为键和值的字典，`key: value`  表示在文件 `key` 中存在匹配正则表达式 `value` 的字符串，*`key` 必须为相对于 `case_path` 的相对路径*。仅在所有文件都存在并且各个文件包含相应的字符串时返回真值

上述 `Euler` 示例的测试用例生成器函数为：

```python
from collections import OrderedDict
import string
import shutil
import os

NX, NY, NZ = 600, 600, 600
NTHREADS = {
  	"mpi-core": 1,
  	"mpi-socket": 12,
  	"mpi-node": 24
}
CPN = 24

def make_case(conf_root, output_root, case_path, test_vector, **kwargs):
    # Expand test vector
    mode, nnodes, test_id = test_vector.values()

    # Make input file by substitute templates
    content = file(os.path.join(conf_root, "templates", "3d.input.template")).read()
    output = os.path.join(case_path, "3d.input")
    var_values = dict(zip(["nx", "ny", "nz"], [NX, NY, NZ]))
    file(output, "w").write(string.Template(content).safe_substitute(var_values))
    # Link data file to case dir since main3d requires it in current working dir
    data_fn = os.path.join(conf_root, "data", "Model.stl")
    link_dir = os.path.join(case_path, "data")
    link_target = os.path.join(link_dir, "Model.stl")
    if os.path.exists(link_dir):
    	shutil.rmtree(link_dir)
    os.makedirs(link_dir)
    os.symlink(os.path.relpath(data_fn, case_path), link_target)

    # Build case descriptions
    bin_path = os.path.join(output_root, "bin", "main3d")
    bin_path = os.path.relpath(bin_path, case_path)
    cmd = [bin_path, "3d.input"]
    envs = {
        "OMP_NUM_THREADS": NTHREADS[mode],
        "KMP_AFFINITY": "compact"
    }
    run = {
        "nnodes": nnodes,
        "procs_per_node": CPN / NTHREADS[mode],
        "tasks_per_proc": NTHREADS[mode],
        "nprocs": nnodes * CPN / NTHREADS[mode]
    }
    results = ["Euler.log"]
    validator = {
      "contains": {
        "Euler.log": "TIME STATISTICS"
      }
    }
    return OrderedDict(zip(["cmd", "envs", "run", "results", "validator"],
                           [cmd, envs, run, results, validator]))
```

### 其他测试向量生成器

在 `project` 中设置 `test_vector_generator` 为 `simple` 或 `cart_product` 时，可在 `TestProjectConfig.json` 中直接设定测试向量，无需编写 python 函数。

#### cart_product_vector_generator

当设置 `test_vector_generator` 为 `cart_product` 时，需在 `TestProjectConfig.json` 中定义 `cart_product_vector_generator` 字典。该字典仅包含一个键 `test_factor_values`，表示各个影响因素的取值。`test_factor_values` 是一个字典，以 `test_factors` 定义的影响因素名称为键，以列表为值，表示按集合的笛卡尔积方式生成所有测试向量。例如，上述 Euler 示例的测试向量生成器可定义为：

```json
{
  "cart_product_vector_generator": {
    "test_factor_values": {
      "mode": ["mpi-core", "mpi-socket", "mpi-node"],
      "nnodes": [1, 2, 4, 8, 16, 32, 64, 128],
      "test_id": [0, 1, 2, 3, 4]
    }
  }
}
```

#### simple_vector_generator

当设置 `test_vector_generator` 为 `simple` 时，需在 `TestProjectConfig.json` 中定义 `simple_vector_generator` 字典。该字典仅包含一个键 `test_vectors`，表示所有的测试向量。`test_vectors` 是一个有列表组成的列表，每个列表项表示一个或一组测试向量。规则为：当该列表项的元素都是基本类型时，表示一个测试向量；当某个元素为列表类型时，表示由各个元素笛卡尔积张成的一组测试向量。例如，上述 Euler 示例的测试向量生成器可定义为：

```json
{
  "simple_vector_generator": {
    "test_vectors": [
      ["mpi-core", [1, 2, 4, 8, 16, 32, 64, 128], [0, 1, 2, 3, 4]],
      ["mpi-socket", [1, 2, 4, 8, 16, 32, 64, 128], [0, 1, 2, 3, 4]],
      ["mpi-node", [1, 2, 4, 8, 16, 32, 64, 128], [0, 1, 2, 3, 4]]
    ]
  }
}
```

### 其他测试用例生成器

在 `project` 中设置 `test_case_generator` 为 `template` 时，可在 `TestProjectConfig.json` 中直接设定测试用例，无需编写 python 函数。

#### template_case_generator

当设置 `test_case_generator` 为 `template` 时，需在 `TestProjectConfig.json` 中定义 `template_case_generator` 字典。