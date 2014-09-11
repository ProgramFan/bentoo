import string

# project_root, cfg_vpath and case_vpath are predefined and mandatory, other
# arguments are user defined and shall coincide with 'args' object in
# TestConfig.json.
#
# Here, each case is defined by (app, model, nnodes, intra_node), binary is
# located at ${app}/bin, input is located at ${app}/input. input is postfixed to
# distiguish between different models, and openmp cases has different inputs.
#
def make_case(project_root, cfg_vpath, case_vpath, bin_name):
    variables = dict(cfg_vpath.items() + case_vpath.items())
    variables["project_root"] = project_root
    variables["bin_name"] = bin_name
    nnodes = variables["nnodes"]
    intra_node = variables["intra_node"]
    procs_per_node, ndsm, nsmp = map(int, intra_node.split("x"))
    tpl_exe = string.Template("${project_root}/${app}/bin/${bin_name}")
    exe = tpl_exe.safe_substitute(variables)
    tpl_inp = string.Template("${project_root}/${app}/input/linadv-3d.input.${model}")
    inp = tpl_inp.safe_substitute(variables)
    if ndsm * nsmp == 12:
        # Pure OpenMP case, postfix input with $nn.omp
        inp = "{0}.{1}.omp".format(inp, nnodes)
    cmd = [exe, inp]
    envs = {
        "JASMIN_NUM_DSM_THREADS": ndsm,
        "JASMIN_NUM_SMP_THREADS": nsmp
    }
    run = {
        "nnodes": nnodes,
        "procs_per_node": procs_per_node,
        "tasks_per_proc": ndsm * nsmp,
        "nprocs": int(nnodes) * procs_per_node
    }
    results = ["LinAdvSL-linadv_3d.input"]
    return dict(cmd=cmd, envs=envs, run=run, results=results)
