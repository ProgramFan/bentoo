#!/usr/bin/env python
#

from collections import OrderedDict
import string
import shutil
import os
import itertools

NX, NY, NZ = 600, 600, 600
NTHREADS = {"mpi-core": 1, "mpi-socket": 12, "mpi-node": 24}
CPN = 24


def make_vectors(conf_root, test_factors, **kwargs):
    assert test_factors == ["mode", "nnodes", "test_id"]
    mode = ["mpi-core", "mpi-socket", "mpi-node"]
    nnodes = [1, 2, 4, 8, 16, 32, 64, 128]
    test_id = range(5)
    return list(itertools.product(mode, nnodes, test_id))


def make_case(conf_root, output_root, case_path, test_vector, **kwargs):
    # Expand test vector
    mode, nnodes, test_id = test_vector.values()

    # Make input file by substitute templates
    content = open(
        os.path.join(conf_root, "templates", "3d.input.template")).read()
    output = os.path.join(output_root, case_path, "3d.input")
    var_values = dict(zip(["nx", "ny", "nz"], [NX, NY, NZ]))
    open(output,
         "w").write(string.Template(content).safe_substitute(var_values))
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
    envs = {"OMP_NUM_THREADS": NTHREADS[mode], "KMP_AFFINITY": "compact"}
    run = {
        "nnodes": nnodes,
        "procs_per_node": CPN / NTHREADS[mode],
        "tasks_per_proc": NTHREADS[mode],
        "nprocs": nnodes * CPN / NTHREADS[mode]
    }
    results = ["Euler.log"]
    validator = {"contains": {"Euler.log": "TIME STATISTICS"}}
    return OrderedDict(
        zip(["cmd", "envs", "run", "results", "validator"],
            [cmd, envs, run, results, validator]))


def main():
    pass


if __name__ == "__main__":
    main()
