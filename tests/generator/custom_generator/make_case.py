#
# Demo generator: you can do anything in make_case, complex calculation for
# case parameters, complex string manipulation, generation files, etc. The
# conf_root, dest_root and vpath will be passed so you know where all your
# files are.
#


from collections import OrderedDict


def make_case(conf_root, output_root, case_path, test_vector, cmd):
    run = {
        "nnodes": 1,
        "procs_per_node": 12 / 1,
        "tasks_per_proc": 1,
        "nprocs": 1 * 12 / 1
    }
    results = ["STDOUT"]
    envs = {
        "OMP_NUM_THREADS": str(1),
        "KMP_AFFINITY": "disabled"
    }
    return OrderedDict(cmd=cmd, envs=envs, run=run, results=results)
