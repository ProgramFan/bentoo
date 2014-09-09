def make_case(case_id, case_name):
    ''' make case for (app, model, nnodes, intra_node) case_id where intra_node
        is similar to "12x1x1"
    '''
    project_root = case_id["project_root"]
    app = case_id["app"]
    nnodes = case_id["nnodes"]
    intra_node = case_id["intra_node"]
    procs_per_node, ndsm, nsmp = map(int, intra_node.split("x"))
    cmd = ["${project_root}/${app}/bin/main2d.lite", "linadv-2d.input"]
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
    results = ["LinAdvSL-linadv_2d.input"]
    return dict(cmd=cmd, envs=envs, run=run, results=results)
