# coding: utf-8
#

import functools
import math


def make_process_grid(nnodes, dim):
    return [nnodes]


conf = {
    "template": {
        "grid": [100, 100, 100],
        "total_mem": "10G"
    },
    "output": [{
        "type": "fixed",
        "nnodes": [1, 2, 16, 128],
        "mem_per_node": ["500M", "5G", "50G"]
    }, {
        "type":
        "scaled",
        "nnodes": [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 3072],
        "mem_per_node": ["500M", "5G", "50G"]
    }]
}


# CASE 1: Arbitrary single block structured grid
#
# In this case, we can generate one grid for any (nnodes, node_memory) pairs by
# constructing a base grid for one node and a process grid. The algorithm is
# stable since we use integer arithmetic for grid calculation.
#
def computeNewGrid(grid, nprocs, proc_memory, new_memory, nnodes, machine):
    '''computeNewGrid

    Compute a new grid for required per-node memory. The grid can be arbitrary.
    '''

    dim = len(grid)
    ncells = functools.reduce(lambda x, y: x * y, grid)
    bytes_per_cell = nprocs * proc_memory * ncells
    new_ncells = new_memory / bytes_per_cell
    nx = int(math.floor(new_ncells**(1.0 / dim)))
    base_grid = [nx for i in range(dim)]
    proc_grid = make_process_grid(nnodes, dim)
    return {
        "nnodes": nnodes,
        "grid": [x * y for x, y in zip(base_grid, proc_grid)]
    }


conf = {
    "template": {
        "type": "predefined",
        "instances": {
            "model1": {
                "dim": 3,
                "total_mem": "500M"
            },
            "model2": {
                "dim": 3,
                "total_mem": "5G"
            },
            "model3": {
                "dim": 3,
                "total_mem": "50G"
            },
        }
    },
    "output": [{
        "type": "fixed",
        "nnodes": [1, 2, 16, 128],
        "mem_per_node": ["500M", "5G", "50G"]
    }, {
        "type": "scaled",
        "nnodes": [3, 6,12,24,48,96,192, 384, 768, 1536, 3072],
        "mem_per_node": ["500M", "5G", "50G"]
    }]
}


# CASE 2: Fixed unstructured grid which can only be refined.
#
# In this case, we are restricted to refine the grid uniformlly. So we need the
# user to provide grid files for a single node and try enlarge them to fit the
# needs. We use only the process grid.
def enlargeGrid(grid, nprocs, proc_memory, new_memory, nnodes):
    dim = len(grid)
    if nprocs * proc_memory > new_memory:
        # The total memory is less than that of
        pass
