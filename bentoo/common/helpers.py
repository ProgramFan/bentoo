# coding: utf-8
#

import functools
import math
import re
import copy


def make_virtual_topology(numa_nodes, cpu_cores, nprocs, nthreads):
    # First flatten threads into tasks and flatten all cores into a core list.
    # Then map task to core round-robinly. Finally we compute the numa nodes
    # and cpu cores of the procs.
    tasks = range(nprocs * nthreads)
    task_to_proc = [t // nthreads for t in tasks]
    cores = []
    for numa_node_id in numa_nodes:
        cores.extend(cpu_cores[numa_node_id])
    task_to_core = [cores[t % len(cores)] for t in tasks]
    core_to_numa_node = dict()
    for k, v in cpu_cores.items():
        for c in v:
            core_to_numa_node[c] = k
    proc_numa_nodes = {p: [] for p in range(nprocs)}
    proc_cores = {p: [] for p in range(nprocs)}
    for t in tasks:
        task_proc_id = task_to_proc[t]
        task_core_id = task_to_core[t]
        proc_numa_nodes[task_proc_id].append(core_to_numa_node[task_core_id])
        proc_cores[task_proc_id].append(task_core_id)
    result = []
    for p in range(nprocs):
        my_numa_nodes = sorted(list(set(proc_numa_nodes[p])))
        my_cores = sorted(proc_cores[p])
        my_topo = {n: [] for n in my_numa_nodes}
        for c in my_cores:
            my_topo[core_to_numa_node[c]].append(c)
        for k, v in my_topo.items():
            my_topo[k] = sorted(list(set(v)))
        result.append(list((n, my_topo[n]) for n in my_numa_nodes))
    return result


def virtual_topology_to_str(topo):
    def contract_numbers(seq):
        if len(seq) == 1:
            return [[seq[0], 1]]
        segs = []
        seq = sorted(seq)
        s = seq[0]
        l = 1
        for i in seq[1:]:
            if s + l == i:
                l += 1
            else:
                segs.append((s, l))
                s = i
                l = 1
        segs.append((s, l))
        return segs

    numa_nodes = []
    node_cores = []
    for v in topo:
        for n, c in v:
            numa_nodes.append(n)
            node_cores.append(contract_numbers(c))
    numa_nodes = contract_numbers(numa_nodes)

    def seg_to_str(seg):
        return "{}-{}".format(seg[0], seg[0] + seg[1] -
                              1) if seg[1] > 1 else "{}".format(seg[0])

    return {
        "numa_nodes_list":
        ",".join(map(seg_to_str, numa_nodes)),
        "cpu_cores_list":
        ";".join(",".join(map(seg_to_str, c)) for c in node_cores)
    }


def parse_topology(cpu_cores, numa_nodes):
    def parse_int_list(s):
        result = []
        for seg in s.split(","):
            rg = seg.split("-")
            if len(rg) == 1:
                result.append(int(rg[0]))
            else:
                result.extend(range(int(rg[0]), int(rg[1]) + 1))
        return result

    numa_nodes = parse_int_list(numa_nodes)
    if not isinstance(cpu_cores, list):
        cpu_cores = cpu_cores.split(";")
    cpu_cores = {i: parse_int_list(cpu_cores[i]) for i in numa_nodes}
    return (cpu_cores, numa_nodes)


def make_jolly_virtual_topology(topo, procs_per_node, nthreads):
    cpu_cores, numa_nodes = parse_topology(topo["cpu_cores"],
                                           topo["numa_nodes"])
    topo = make_virtual_topology(numa_nodes, cpu_cores, procs_per_node,
                                 nthreads)
    vtopo = virtual_topology_to_str(topo)
    return {
        "JOLLY_CPU_CORES_LIST": vtopo["cpu_cores_list"],
        "JOLLY_NUMA_NODES_LIST": vtopo["numa_nodes_list"]
    }


def make_process_grid(n, dim=3):
    def is_prime(x):
        if x == 1:
            return True
        for i in range(2, x // 2 + 1):
            if x % i == 0:
                return False
        return True

    def prime_factors(x):
        if is_prime(x):
            return [x]
        result = []
        for v in range(2, x // 2 + 1):
            if not is_prime(v):
                continue
            if n % v == 0:
                result.append(v)
        return result

    def min_index(l):
        v = l[0]
        i = 0
        for i1, v1 in enumerate(l):
            if v1 < v:
                i = i1
                v = v1
        return (i, v)

    def max_index(l):
        v = l[0]
        i = 0
        for i1, v1 in enumerate(l):
            if v1 > v:
                i = i1
                v = v1
        return (i, v)

    all_primes = prime_factors(n)
    result = [1 for i in range(dim)]
    if n == 1:
        return result
    elif n == 2:
        result[0] = n
        return result
    i = 0
    n1 = n
    for v in all_primes:
        while n1 % v == 0:
            result[i % dim] *= v
            i += 1
            n1 //= v
    result = sorted(result, reverse=True)
    for v in all_primes:
        while True:
            max_idx, max_val = max_index(result)
            min_idx, min_val = min_index(result)
            if max_val > min_val * v and max_val % v == 0:
                result[max_idx] //= v
                result[min_idx] *= v
            else:
                break
    assert functools.reduce(lambda x, y: x * y, result) == n
    return sorted(result, reverse=True)


def sizeToFloat(s):
    if isinstance(s, (int, float)):
        return float(s)
    unitValue = {"b": 1, "k": 1024, "m": 1024 * 1024, "g": 1024 * 1024 * 1024}
    regex = re.compile(
        r"(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)([kmgKMG](?:i?[Bb])?)?")
    m = regex.match(s)
    if m is None:
        raise RuntimeError("Invalid size representation '%s'" % s)
    value = float(m.group(1))
    unit = m.group(2)
    unit = unit[0].lower() if unit else 'b'
    return value * unitValue[unit]


def floatToSize(f):
    if not isinstance(f, (int, float)):
        return f
    if f < 1024:
        return "{:.1f}".format(f)
    elif f < 1024 * 1024:
        return "{:.1f}K".format(f / 1024.0**1)
    elif f < 1024 * 1024 * 1024:
        return "{:.1f}M".format(f / 1024.0**2)
    else:
        return "{:.1f}G".format(f / 1024.0**3)


class StructuredGridModelResizer(object):
    '''Resize a structured grid model

    This resizer assumes the model uses a structured grid and the grid can be
    regrided arbitrarily to fit any total memory requirements.
    '''
    def __init__(self, grid, total_mem):
        '''Initialize the resizer

        :grid: The shape of the grid, integer list
        :total_mem: The total memory of the model, float or string. Strings will
        be recogonized as '13.3K/KB/Kib/k/kb'"
        '''
        self.grid = grid
        self.dim = len(grid)
        self.total_mem = sizeToFloat(total_mem)

    def exactResize(self):
        '''Test if the resizer can resize exactly to the required mem_per_node
        and nnodes'''
        return True

    def resize(self, mem_per_node, nnodes=1):
        '''Resize the model to reach a certain memory per node

        :mem_per_node: The memory per node required, float or string.
        :nnodes: The number of nodes required

        :return: The new grid and nnodes for the model.
        '''
        mem_per_node = sizeToFloat(mem_per_node)
        ncells = functools.reduce(lambda x, y: x * y, self.grid)
        bytes_per_cell = self.total_mem / ncells
        new_ncells = mem_per_node / bytes_per_cell
        nx = int(math.floor(new_ncells**(1.0 / self.dim)))
        base_grid = [nx for i in range(self.dim)]
        new_ncells = functools.reduce(lambda x, y: x * y, base_grid)
        new_mem_per_node = bytes_per_cell * new_ncells
        proc_grid = make_process_grid(nnodes, self.dim)
        return {
            "nnodes": nnodes,
            "grid": [x * y for x, y in zip(base_grid, proc_grid)],
            "mem_per_node": floatToSize(new_mem_per_node),
            "index_": 0
        }

    def next(self, model):
        '''Find the next model with the same mem_per_node in the reference model

        The next model will be the model with the same mem_per_node but a
        larger nnodes.
        '''
        result = copy.deepcopy(model)
        result["nnodes"] *= 2
        result["grid"][result["index_"]] *= 2
        result["index_"] = (result["index_"] + 1) % self.dim
        return result


class UnstructuredGridModelResizer(object):
    '''Resize an unstructured grid model

    This resizer assumes the grid is unstructured and one can only refine
    uniformlly the grid to reach a given size.
    '''
    def __init__(self, dim, total_mem):
        '''Initialize the resizer

        :dim: The dim of the model, integer
        :total_mem: The total memory of the model, float or string. Strings will
        be recogonized as '13.3K/KB/Kib/k/kb'"
        '''
        self.dim = int(dim)
        self.total_mem = sizeToFloat(total_mem)
        self.stride = 2**self.dim

    def exactResize(self):
        '''Test if the resizer can resize exactly to the required mem_per_node
        and nnodes'''
        return False

    def resize(self, mem_per_node, nnodes=1):
        '''Resize the model to reach a certain memory per node

        :mem_per_node: The memory per node required, float or string.
        :nnodes: The number of nodes required

        :return: The new grid and nnodes for the model.

        Note: memory per node shall never exceed the requested.
        '''
        mem_per_node = sizeToFloat(mem_per_node)
        total_mem_req = mem_per_node * nnodes
        rel = math.fabs(2 * (total_mem_req - self.total_mem) /
                        (self.total_mem + total_mem_req))
        # If the error is so small or if request is within 25% larger than the
        # model, use it.
        if rel < 0.01 or (self.total_mem < total_mem_req and rel < 0.25):
            return {
                "nrefines": 0,
                "nnodes": nnodes,
                "mem_per_node": floatToSize(self.total_mem / nnodes)
            }
        # If the request is bigger, enlarge the model (may change nnodes as
        # well). Otherwise, change the nnodes to satisfy the memory per node.
        if self.total_mem < total_mem_req:
            ratio = total_mem_req / self.total_mem
            i = int(math.floor(math.log(ratio, self.stride)))
            real_mem = self.total_mem * self.stride**i
            real_mem_per_node = real_mem / nnodes
            if real_mem_per_node * 2 < mem_per_node:
                # The resized model is too small from the required size, we have
                # to enlarge more and change the nnodes as well.
                i += 1
                real_mem = self.total_mem * self.stride**i
                real_mem_per_node = real_mem / nnodes
                assert real_mem_per_node > mem_per_node
                new_nnodes = int(math.ceil(real_mem / total_mem_req) * nnodes)
                new_nnodes = 2**int(math.ceil(math.log2(new_nnodes)))
                new_mem_per_node = real_mem / new_nnodes
                return {
                    "nrefines": i,
                    "nnodes": new_nnodes,
                    "mem_per_node": floatToSize(new_mem_per_node)
                }
            else:
                return {
                    "nrefines": i,
                    "nnodes": nnodes,
                    "mem_per_node": floatToSize(real_mem_per_node)
                }
        else:
            # compute nnodes for the nearest mem_per_node
            nnodes = int(math.ceil(self.total_mem / mem_per_node))
            # find the nearest 2's multiple
            nnodes = 2**int(math.ceil(math.log2(nnodes)))
            mem_per_node = self.total_mem / nnodes
            return {
                "nrefines": 0,
                "nnodes": nnodes,
                "mem_per_node": floatToSize(mem_per_node)
            }

    def next(self, model):
        '''Find the next model with the same mem_per_node in the reference model

        The next model will be the model with the same mem_per_node but a
        larger nnodes.
        '''
        result = copy.deepcopy(model)
        result["nnodes"] *= self.stride
        result["nrefines"] += 1
        return result


class OmniModelResizer(object):
    '''Resize an arbitrary model

    This resizer does not make any assumptions on the grid. It just search
    through the spec for a best match of a given request.
    '''
    def __init__(self, model_db, max_nnodes):
        '''Initialize the resizer

        :model_db: The database of available models
        '''
        self.resizers = []
        self.fixed_models = []
        self.can_resize_exactly = False
        for model in model_db:
            assert isinstance(model, dict)
            assert "tag" in model
            if not model.get("resizable", False):
                m = copy.deepcopy(model)
                m["resizer_id_"] = None
                self.fixed_models.append(m)
                continue
            assert model["type"] in ("structured_grid", "unstructured_grid")
            if model["type"] == "structured_grid":
                resizer = StructuredGridModelResizer(model["grid"],
                                                     model["total_mem"])
                self.resizers.append(resizer)
                self.can_resize_exactly = True
            else:
                resizer = UnstructuredGridModelResizer(model["dim"],
                                                       model["total_mem"])
                self.resizers.append(resizer)

    def exactResize(self):
        '''Test if the resizer can resize exactly to the required mem_per_node
        and nnodes'''
        return self.can_resize_exactly

    def resize(self, mem_per_node, nnodes=1):
        '''Resize the model to reach a certain memory per node

        :mem_per_node: The memory per node required, float or string.
        :nnodes: The number of nodes required

        :return: The new grid and nnodes for the model.

        Note: memory per node shall never exceed the requested.
        '''
        # The logic of resize: the model database contains two kinds of models:
        # models with fixed nnodes and mem_per_node, and resizers. On any resize
        # request, the fixed models are searched first, the results with the
        # best match (within 20% of the requested size) is returned. Otherwise,
        # the resizers are tried and the best result (with the best mem_per_node
        # and nnodes match) is returned. If Nothing is found, an error will
        # occur.
        mem_per_node_req = sizeToFloat(mem_per_node)
        candidates = []
        for model in self.fixed_models:
            mem_per_node_real = sizeToFloat(model["mem_per_node"])
            nnodes_real = model["nnodes"]
            ratio = mem_per_node_real / mem_per_node_req
            if nnodes_real == nnodes and ratio > 0.8 and ratio <= 1:
                candidates.append(model)
        if candidates:
            result = max(candidates,
                         key=lambda x: sizeToFloat(x["mem_per_node"]) /
                         mem_per_node_req)
            return copy.deepcopy(result)

        for i, resizer in enumerate(self.resizers):
            m = resizer.resize(mem_per_node, nnodes)
            m["resizer_id_"] = i
            candidates.append(m)
        # Indication of how good a candidate matches the request. Smaller is
        # better.
        def deviation(x):
            s1 = 1 - sizeToFloat(x["mem_per_node"]) / mem_per_node_req
            assert s1 >= 0
            s2 = 1 - math.fabs(x["nnodes"] - nnodes) / (x["nnodes"] + nnodes)
            return 0.4 * s1 + 0.6 * s2

        if candidates:
            result = min(candidates, key=deviation)
            return result
        else:
            raise RuntimeError(
                "Can not find proper cases for mem_per_node %s with %d nodes" %
                (mem_per_node, nnodes))

    def next(self, model):
        '''Find the next model with the same mem_per_node in the reference model

        The next model will be the model with the same mem_per_node but a
        larger nnodes.
        '''
        # The logic of resize: The model recorded it is fixed or the index of
        # resizer. In case of a resizer, the resizer will respond a next. In
        # case of fixed, the fixed models are searched first, the results with
        # the best match (just larger than nnodes and within 5% of the requested
        # size) is returned. Otherwise, all resizers are tried and the best
        # result (with the best mem_per_node and nnodes match) is returned. If
        # Nothing is found, an error will occur.
        if model.get("resizer_id_", None) is not None:
            m = self.resizers[model["resizer_id_"]].next(model)
            m["resizer_id_"] = model["resizer_id_"]
            return m
        curr_mem_per_node = sizeToFloat(model["mem_per_node"])
        curr_nnodes = model["nnodes"]
        candidates = []
        for m in self.fixed_models:
            mem_per_node = sizeToFloat(m["mem_per_node"])
            nnodes = m["nnodes"]
            ratio = mem_per_node / curr_mem_per_node
            if nnodes > curr_nnodes and ratio > 0.95 and ratio <= 1.05:
                candidates.append(m)
        if candidates:
            result = min(candidates, key=lambda x: int(x["nnodes"]))
            return copy.deepcopy(result)
        if self.resizers:
            mem_per_node_req = sizeToFloat(model["mem_per_node"])
            for i, resizer in enumerate(self.resizers):
                m = resizer.resize(mem_per_node_req, curr_nnodes * 2)
                ratio = sizeToFloat(m["mem_per_node"]) / curr_mem_per_node
                if m["nnodes"] > curr_nnodes and ratio >= 0.95 and ratio <= 1.05:
                    m["resizer_id_"] = i
                    candidates.append(m)
                    continue
                m = resizer.resize(mem_per_node_req, curr_nnodes * 4)
                ratio = sizeToFloat(m["mem_per_node"]) / curr_mem_per_node
                if m["nnodes"] > curr_nnodes and ratio >= 0.95 and ratio <= 1.05:
                    m["resizer_id_"] = i
                    candidates.append(m)
                    continue
                m = resizer.resize(mem_per_node_req, curr_nnodes * 8)
                ratio = sizeToFloat(m["mem_per_node"]) / curr_mem_per_node
                if m["nnodes"] > curr_nnodes and ratio >= 0.95 and ratio <= 1.05:
                    m["resizer_id_"] = i
                    candidates.append(m)

            def deviation(x):
                s1 = 1 - sizeToFloat(x["mem_per_node"]) / mem_per_node_req
                return s1

            if candidates:
                result = min(candidates, key=deviation)
                return result

        raise StopIteration("No more proper cases for mem_per_node %s" %
                            model["mem_per_node"])
