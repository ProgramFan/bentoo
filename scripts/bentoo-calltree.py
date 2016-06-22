#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#

'''
calltree.py - Call tree manipulator

This script manipulates call tree generated by JASMIN CallTreeManager. It
prints, folds, and limit depth of the input call tree.
'''

import argparse
import copy
import json
import fnmatch
import hashlib

from collections import OrderedDict


class TreeNode(object):

    @classmethod
    def serialize(cls, node):
        if not node:
            return None
        data = OrderedDict()
        data["id"] = node.id
        data["cycle"] = node.cycle
        data["children"] = []
        for c in node.children:
            child = cls.serialize(c)
            data["children"].append(child)
        return data

    @classmethod
    def deserialize(cls, data):
        if not data:
            return None
        node = TreeNode(data["id"], data["cycle"])
        for c in data["children"]:
            child = cls.deserialize(c)
            node.append_child(child)
        return node

    def __init__(self, id, cycle=1):
        self.id = id
        self.cycle = cycle
        self.children = []
        self.update_digest()

    def append_child(self, child):
        assert isinstance(child, TreeNode)
        self.children.append(child)
        self.update_digest()

    def update_digest(self):
        m = hashlib.md5()
        m.update(str(self.id))
        for c in self.children:
            m.update(str(c.digest))
        self.digest = m.digest()

    def __repr__(self):
        result = []
        result.append(" %s %s" % (self.id, self.cycle))
        for c in self.children:
            child_repr = repr(c).split("\n")
            result.extend(map(lambda x: "-%s" % x, child_repr))
        return "\n".join(result)

    def __eq__(self, x):
        return self.digest == x.digest

    def __ne__(self, x):
        return self.digest != x.digest

    def __le__(self, x):
        if self.id != x.id:
            return False
        me = [c.digest for c in self.children]
        other = [c.digest for c in x.children]
        index = 0
        for item in me:
            if item not in other[index:]:
                return False
            index = other.index(item, index)
        return True

    def __lt__(self, x):
        if len(self.children) >= len(x.children):
            return False
        return self <= x

    def __ge__(self, x):
        if self.id != x.id:
            return False
        me = [c.digest for c in self.children]
        other = [c.digest for c in x.children]
        index = 0
        for item in other:
            if item not in me[index:]:
                return False
            index = me.index(item, index)
        return True

    def __gt__(self, x):
        if len(self.children) <= len(x.children):
            return False
        return self <= x


def fold_tree(tree, keep_level=None, remove_calls=None, cascade=False):

    def fold_tree_recursive(tree):
        if not tree:
            return None
        folded_children = []
        for c in tree.children:
            folded_children.append(fold_tree_recursive(c))
        new_children = []
        if folded_children:
            new_children = [folded_children[0]]
            for i in xrange(1, len(folded_children)):
                if folded_children[i] != new_children[-1]:
                    new_children.append(folded_children[i])
        new_tree = TreeNode(tree.id, tree.cycle)
        for c in new_children:
            new_tree.append_child(c)
        return new_tree

    def cascase_tree_recursive(tree):
        def in_full_order_set(elem, array):
            if not array:
                return True
            for c in array:
                if elem <= c or elem >= c:
                    return True
            return False

        def get_maximum(array):
            tmp = list(array)
            tmp.sort()
            return tmp[-1]

        if not tree:
            return None
        folded_children = []
        for c in tree.children:
            folded_children.append(cascase_tree_recursive(c))

        new_children = []
        if folded_children:
            poss = []
            pos = []
            for c in folded_children:
                if in_full_order_set(c, pos):
                    pos.append(c)
                else:
                    poss.append(pos)
                    pos = [c]
            poss.append(pos)
            for c in poss:
                new_children.append(get_maximum(c))

        new_tree = TreeNode(tree.id, tree.cycle)
        for c in new_children:
            new_tree.append_child(c)
        return new_tree

    def cut_tree_recursive(tree, curr_level, max_level):
        if not tree:
            return None
        if curr_level >= max_level:
            return None
        children = []
        for c in tree.children:
            child = cut_tree_recursive(c, curr_level + 1, max_level)
            if child:
                children.append(child)
        new_tree = TreeNode(tree.id, tree.cycle)
        for c in children:
            new_tree.append_child(c)
        return new_tree

    def remove_node_recursive(tree, patterns):
        if not tree:
            return None
        for c in patterns:
            if fnmatch.fnmatch(tree.id, c):
                return None
        children = []
        for c in tree.children:
            child = remove_node_recursive(c, patterns)
            if child:
                children.append(child)
        new_tree = TreeNode(tree.id, tree.cycle)
        for c in children:
            new_tree.append_child(c)
        return new_tree

    if remove_calls:
        tree = remove_node_recursive(tree, remove_calls)
    if keep_level:
        tree = cut_tree_recursive(tree, 0, keep_level)
    if cascade:
        return cascase_tree_recursive(tree)
    else:
        return fold_tree_recursive(tree)


def print_tree(tree, max_level=None):
    def print_tree_recursive(tree, level, max_level):
        if max_level and level > max_level:
            return
        print "--" * level, tree.id, tree.cycle
        for c in tree.children:
            print_tree_recursive(c, level + 1, max_level)
    print_tree_recursive(tree, 1, max_level)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("call_tree",
                        help="Call tree file (json) generated by JASMIN")
    parser.add_argument("--save", help="Output filename", default=None)
    parser.add_argument("--max-depth", default=None, type=int,
                        help="Max depth for output tree")
    parser.add_argument("--keep-level", default=None, type=int,
                        help="Max levels to keep when folding tree")
    parser.add_argument("--remove-calls", default=[], nargs="+",
                        help="Remove matched calls, supports shell wildcards")
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--fold", action="store_true", help="Fold tree")
    grp.add_argument("--cascade", action="store_true", help="Cascade tree")

    args = parser.parse_args()

    data = json.load(file(args.call_tree), object_hook=OrderedDict)
    tree = TreeNode.deserialize(data)
    if tree.id == "ROOT":
        tree = tree.children[0]
    if args.fold or args.cascade:
        tree = fold_tree(tree, args.keep_level,
                         args.remove_calls, args.cascade)
    if args.save:
        data = TreeNode.serialize(tree)
        json.dump(data, file(args.save, "w"), indent=2)
    print_tree(tree, args.max_depth)


if __name__ == "__main__":
    main()
