# coding: utf-8
#

import functools
import math
import re
import copy


def make_process_grid(n, dim):
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

    def resize(self, mem_per_node, nnodes=1):
        '''Resize the model to reach a certain memory per node

        :mem_per_node: The memory per node required, float or string.
        :nnodes: The number of nodes required

        :return: The new grid and nnodes for the model.
        '''
        mem_per_node = sizeToFloat(mem_per_node)
        total_mem_req = mem_per_node * nnodes
        rel = math.fabs(2 * (total_mem_req - self.total_mem) /
                        (self.total_mem + total_mem_req))
        # If the request is within 25% of the original model, use it.
        if rel < 0.25:
            print("direct return")
            return {
                "nrefines": 0,
                "nnodes": nnodes,
                "mem_per_node": floatToSize(self.total_mem / nnodes)
            }
        # If the request is bigger, enlarge the model (may change nnodes as
        # well). Otherwise, change the nnodes to satisfy the memory per node.
        if total_mem_req > self.total_mem:
            ratio = total_mem_req / self.total_mem
            i = int(math.floor(math.log(ratio, self.stride)))
            real_mem = self.total_mem * self.stride**i
            real_mem_per_node = real_mem / nnodes
            if real_mem_per_node * 2 < mem_per_node:
                print("adjust nnodes")
                # The resized model is too small from the required size, we have
                # to enlarge more and change the nnodes as well.
                i += 1
                real_mem = self.total_mem * self.stride**i
                real_mem_per_node = real_mem / nnodes
                assert real_mem_per_node > mem_per_node
                new_nnodes = int(math.ceil(real_mem / total_mem_req) * nnodes)
                new_nnodes = 2 ** int(math.ceil(math.log2(new_nnodes)))
                new_mem_per_node = real_mem / new_nnodes
                return {
                    "nrefines": i,
                    "nnodes": new_nnodes,
                    "mem_per_node": floatToSize(new_mem_per_node)
                }
            else:
                print("No adjust nnodes")
                return {
                    "nrefines": i,
                    "nnodes": nnodes,
                    "mem_per_node": floatToSize(real_mem_per_node)
                }
        else:
            print("simple nnodes adjust")
            # compute nnodes for the nearest mem_per_node
            nnodes = int(math.ceil(self.total_mem / mem_per_node))
            # find the nearest 2's multiple
            nnodes = 2 ** int(math.ceil(math.log2(nnodes)))
            mem_per_node = self.total_mem / nnodes
            return {
                "nrefines": 0,
                "nnodes": nnodes,
                "mem_per_node": floatToSize(mem_per_node)
            }

    def next(self, model):
        result = copy.deepcopy(model)
        result["nnodes"] *= self.stride
        result["nrefines"] += 1
        return result
