#
# Demo generator: you can do anything in make_case, complex calculation for case
# parameters, complex string manipulation, generation files, etc. The conf_root,
# dest_root and vpath will be passed so you know where all your files are.
#

import os


def make_case(conf_root, dest_root, cfg_vpath, case_vpath, cmd):
    nnodes, nthreads = map(int, case_vpath.values())
    casepath = os.path.join(".", *(cfg_vpath.values()+case_vpath.values()))
    relroot = os.path.relpath(".", casepath)
    real_cmd = cmd + [relroot]
    run = {
        "nnodes": nnodes,
        "procs_per_node": 12 / nthreads,
        "tasks_per_proc": nthreads,
        "nprocs": nnodes * 12 / nthreads
    }
    results = ["STDOUT"]
    envs = {
        "OMP_NUM_THREADS": str(nthreads),
        "KMP_AFFINITY": "disabled"
    }
    return dict(cmd=real_cmd, envs=envs, run=run, results=results)
