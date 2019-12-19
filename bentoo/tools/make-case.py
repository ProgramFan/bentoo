#!/usr/bin/env python3
#


from __future__ import division
from builtins import range
from builtins import object
from past.utils import old_div
class ScalingCaseMaker(object):
    '''A test vector generator for scaling tests'''
    def __init__(self, ref_mem_mb, ref_nnodes, min_mem, max_mem):
        self.min_mem = min_mem
        self.max_mem = max_mem
        self.ref_mem = ref_mem
        self.multiplier = 2

    def make_strong_scaling_stress_cases(self, min_nodes, max_nodes, max_steps):
        '''Generate cases for strong scaling limit test

        Strong scaling limit tests uses a series of strong scaling tests from
        the maximum memory per node to minimum memory per node, and scales from
        the starting node count to two orders of mangnitidue to identify the
        strong scaling limit of all possible cases. For example, we want to
        investigate the strong scaling from 4 nodes on, and the reference case
        occupies 1/4 of node memory on 4 nodes. The cases are:

            [[(1, 4), (1, 8), ..., (1, 512)],
             [(0, 4), (0, 8), ..., (0, 512)],
             [(-1, 4), (-1, 8), ..., (-1, 512)],
             [(-2, 4), (-2, 8), ..., (-2, 512)],
             [(-3, 4), (-3, 8), ..., (-3, 512)]]

        '''
        cases = []

        mem = self.ref_mem
        nnodes = self.ref_nnodes
        mpn = old_div(mem, nnodes)
        while mpn <= self.max_mpn:
            ratio += 1
            mpn *= 2
        ration -= 1

        mpn = max_mpn
        ratio = 0
        while mpn >= min_mpn:
            cases.extend((ratio, min_nodes * 2**x)
                        for x in range(0, max_node_multipler, steping))
            ratio = ratio - steping
            mpn = max_mpn * 2.0**ratio
        #print(cases)

    def make_strong_weak_matrix_cases(self, min_nodes, max_nodes, max_steps):
        # then generate all expanding cases
        ratio = steping
        nnodes = min_nodes * 2**steping
        # Find the maximal possible starting nnodes so that the largest case won't
        # exceed max_nodes.
        max_start_nnodes = min_nodes
        while max_start_nnodes * 2**(max_node_multipler - steping) <= max_nodes:
            max_start_nnodes = max_start_nnodes * 2**steping
        max_start_nnodes = old_div(max_start_nnodes, 2**steping)
        while nnodes <= max_start_nnodes:
            cases.extend((ratio, nnodes * 2**x)
                        for x in range(0, max_node_multipler, steping))
            ratio = ratio + steping
            nnodes = nnodes * 2**steping

    def make_weak_scaling_stress_cases(self, min_nodes, max_nodes, max_steps):
        # then put more into weak scaling cases
        all_weak = []
        mpn = max_mpn
        ratio = 0
        while mpn >= min_mpn:
            all_weak.append((ratio, min_nodes))
            ratio = ratio - steping
            mpn = max_mpn * 2.0**ratio
        chosen = [
            int(i * float(len(all_weak) - 1) / float(nweaks))
            for i in range(nweaks)
        ]
        chosen = [all_weak[i] for i in chosen]
        max_weak_portion = 0
        while min_nodes * 2**max_weak_portion <= max_nodes:
            max_weak_portion = max_weak_portion + steping
        max_weak_portion = max_weak_portion - steping
        for item in chosen:
            cases.extend((ratio + n, min_nodes * 2**n)
                        for n in range(0, max_weak_portion + 1, steping))

        cases = sorted(list(set(cases)))


def main():
    pass


if __name__ == "__main__":
    main()
