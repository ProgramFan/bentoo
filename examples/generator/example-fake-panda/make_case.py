#
# Demo generator: you can do anything in make_case, complex calculation for
# case parameters, complex string manipulation, generation files, etc. The
# conf_root, dest_root and vpath will be passed so you know where all your
# files are.
#

import os
import string
from collections import OrderedDict
import bentoo.common.helpers as helpers


def make_case(conf_root, output_root, case_path, test_vector, case_info,
              nthreads, **kwargs):
    # Expand test vector
    model, bench, _, _, nnodes, ncores, _ = test_vector.values()

    # Prepare case files
    input_fn = "{}.input".format(model)
    input_tpl = os.path.join(conf_root, "inputs", input_fn + ".template")
    with open(input_tpl) as f:
        input_tpl = string.Template(f.read())
    mesh_fn = case_info["tag"]
    nrefines = case_info.get("nrefines", 0)
    var_values = {
        "mesh":
        os.path.relpath(os.path.join(output_root, "meshes", mesh_fn),
                        case_path),
        "nrefines":
        nrefines
    }
    with open(os.path.join(case_path, input_fn), 'w') as f:
        f.write(input_tpl.safe_substitute(var_values))

    # Build case descriptions
    #
    # Important: Please return 'cmd', 'run', 'results' and 'envs'
    bin_path = os.path.join(output_root, "bin", "panda_sd")
    bin_path = os.path.relpath(bin_path, case_path)
    cmd = [bin_path, input_fn]

    cores_per_node = case_info["sys_cores_per_node"]
    topo = {
        "cpu_cores": case_info["sys_node_cpu_cores"],
        "numa_nodes": case_info["sys_node_numa_nodes"]
    }
    if bench == "onenode":
        envs = {"OMP_NUM_THREADS": 1}
        run = {
            "nnodes": 1,
            "procs_per_node": ncores,
            "tasks_per_proc": 1,
            "nprocs": ncores
        }
    else:
        envs = {
            "OMP_NUM_THREADS": nthreads,
            "JOLLY_NUM_DSM_THREADS": 1,
            "JOLLY_NUM_SMP_THREADS": nthreads,
            "JAUMIN_NUM_THREADS": nthreads
        }
        ppn = cores_per_node // nthreads
        envs.update(helpers.make_jolly_virtual_topology(topo, ppn, nthreads))
        run = {
            "nnodes": nnodes,
            "procs_per_node": ppn,
            "tasks_per_proc": nthreads,
            "nprocs": ncores // nthreads
        }

    results = ['jems_td.log']
    validator = {"contains": {"jems_td.log": "TIME STATISTICS"}}

    return OrderedDict(
        zip(["cmd", "envs", "run", "results", "validator"],
            [cmd, envs, run, results, validator]))


def main():
    pass


if __name__ == "__main__":
    main()
