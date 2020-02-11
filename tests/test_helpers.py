# coding: utf-8

import unittest
import bentoo.common.helpers2 as helpers


class TestHelpers2(unittest.TestCase):
    def test_make_process_grid(self):
        # Each case as: ((nnodes, dim), grid)
        cases = [([6, 2], [3, 2]), ([2, 2], [2, 1]), ([4, 2], [2, 2]),
                 ([8, 2], [4, 2]), ([3072, 2], [64, 48]), ([6, 3], [3, 2, 1]),
                 ([2, 3], [2, 1, 1]), ([16, 3], [4, 2, 2])]
        for args, expect in cases:
            self.assertEqual(helpers.make_process_grid(*args), expect)

    def test_UnstructuredGridModelResizer(self):
        config = [{
            "dim": 3,
            "total_mem": "5G",
            # Each case as: ((mem_per_node, nnodes), (nrefines, nnodes,
            # mem_per_node))
            "cases": [
                (("5.1G", 1), (0, 1, "5.0G")),
                (("5.0G", 1), (0, 1, "5.0G")),
                (("4.5G", 1), (0, 2, "2.5G")),
                (("500M", 1), (0, 16, "320.0M")),
                (("500M", 8), (0, 16, "320.0M")),
                (("500M", 16), (0, 16, "320.0M")),
                (("500M", 64), (1, 128, "320.0M")),
            ]
        }]
        for conf in config:
            resizer = helpers.UnstructuredGridModelResizer(
                conf["dim"], conf["total_mem"])
            for args, expect in conf["cases"]:
                get = resizer.resize(*args)
                get = [get[x] for x in ("nrefines", "nnodes", "mem_per_node")]
                self.assertEqual(get, list(expect))
