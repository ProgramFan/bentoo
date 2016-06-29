#!/usr/bin/env python2.7
# coding: utf-8

import argparse
import importlib
import itertools
import json
import os
import re
import shutil
import sys
import string

from collections import OrderedDict


def parse_json(fn):
    '''Parse json object

    This function parses a JSON file. Unlike the builtin `json` module, it
    supports "//" like comments, uses 'str' for string representation and
    preserves the key orders.

    Args:
        fn (str): Name of the file to parse.

    Returns:
        OrderedDict: A dict representing the file content.

    '''
    def ununicodify(obj):
        result = None
        if isinstance(obj, OrderedDict):
            result = OrderedDict()
            for k, v in obj.iteritems():
                k1 = str(k) if isinstance(k, unicode) else k
                result[k1] = ununicodify(v)
        elif isinstance(obj, list):
            result = []
            for v in obj:
                result.append(ununicodify(v))
        elif isinstance(obj, unicode):
            result = str(obj)
        else:
            result = obj
        return result
    content = file(fn).read()
    content = re.sub(r"//.*", "", content)
    return ununicodify(json.loads(content, object_pairs_hook=OrderedDict))


class SimpleVectorGenerator:
    '''Simple test vector generator

    Generates a collection of test vectors by iterating over provided test
    vector space and expanding possible compacts.

    Args:
        test_factors (list): test factor names.
        raw_vectors (list): test vector collection.
            Each element shall be a list denoting the factor values. Its
            element is either a blob or a list. If it's a list, it denotes
            a range of possible values for the related test factor.

    Examples:
        A straight forward generator:

            SimpleVectorGenerator(["A", "B"], [[1, 2], [1, 3], [2, 3]])

        A compact representation:

            SimpleVectorGenerator(["A", "B"], [[1, [2, 3]], [2, 3]])

    '''

    def __init__(self, test_factors, raw_vectors=None):
        self.test_factors = test_factors
        self.raw_vectors = raw_vectors if raw_vectors else []

    def iteritems(self):
        '''An iterator over the range of test vectors

        Yields:
            OrderedDict: a test vector.

            OrderedDict.values() is the test factor values and
            OrderedDict.keys() is the test factor names.

        '''
        # expand each vector to support `[0, [1, 2], [3, 4]]`
        for item in self.raw_vectors:
            iters = [x if isinstance(x, list) else [x] for x in item]
            for v in itertools.product(*iters):
                yield OrderedDict(zip(self.test_factors, v))


class CartProductVectorGenerator:
    '''Cartetian product test vector generator

    Generate a collection of test vectors by iterating a Cartetian product
    of possible test factor values.

    Args:
        test_factors (list): test factor names.
        factor_values (list): test factor value ranges.
            (k, v) denotes (test factor name, test factor values)

    '''

    def __init__(self, test_factors, factor_values):
        self.test_factors = test_factors
        self.factor_values = factor_values

    def iteritems(self):
        '''An iterator over the range of test vectors

        Yields:
            OrderedDict: a test vector.

            OrderedDict.values() is the test factor values and
            OrderedDict.keys() is the test factor names.

        '''
        factor_values = [self.factor_values[k] for k in self.test_factors]
        for v in itertools.product(*factor_values):
            yield OrderedDict(zip(self.test_factors, v))


def replace_template(template, varvalues):
    return string.Template(str(template)).safe_substitute(varvalues)


def safe_eval(expr):
    try:
        result = eval(str(expr))
    except ZeroDivisionError:
        result = 0
    except NameError:
        result = str(expr)
    return result


class TemplateCaseGenerator(object):
    def __init__(self, template):
        assert("case_spec" in template)
        self.template = template.copy()
        if "copy_files" not in self.template:
            self.template["copy_files"] = OrderedDict()
        assert(isinstance(self.template["copy_files"], OrderedDict))
        if "inst_files" not in self.template:
            self.template["inst_files"] = OrderedDict()

    def make_case(self, conf_root, output_root, case_path, test_vector):
        '''Generate a test case according to the specified test vector'''
        # copy case files: each file is defiend as (src, dst), where src is
        # relative to conf_root and dst is relative to case_path.
        for src, dst in self.template["copy_files"].iteritems():
            srcpath = replace_template(src, test_vector)
            dstpath = replace_template(dst, test_vector)
            assert(not os.path.isabs(srcpath))
            assert(not os.path.isabs(dstpath))
            srcpath = os.path.join(conf_root, srcpath)
            dstpath = os.path.join(case_path, dstpath)
            if os.path.exists(dstpath):
                if os.path.isdir(dstpath):
                    shutil.rmtree(dstpath)
                else:
                    os.remove(dstpath)
            if not os.path.exists(srcpath):
                raise ValueError("Case file '%s' not found" % srcpath)
            if os.path.isdir(srcpath):
                shutil.copytree(srcpath, dstpath)
            else:
                shutil.copyfile(srcpath, dstpath)

        # instantiate template files based on template substitution
        inst_files = self.template["inst_files"]
        if inst_files:
            var_values = {}
            for k, v in inst_files["variables"].iteritems():
                v = replace_template(v, test_vector)
                v = safe_eval(v)
                var_values[k] = v
            for src, dst in inst_files["templates"].iteritems():
                srcpath = replace_template(src, test_vector)
                dstpath = replace_template(dst, test_vector)
                assert(not os.path.isabs(srcpath))
                assert(not os.path.isabs(dstpath))
                srcpath = os.path.join(conf_root, srcpath)
                dstpath = os.path.join(case_path, dstpath)
                if not os.path.exists(srcpath):
                    raise ValueError("Template '%s' does not exist" % srcpath)
                if not os.path.isfile(srcpath):
                    raise ValueError("Template '%s' is not a file" % srcpath)
                if os.path.exists(dstpath):
                    os.remove(dstpath)
                if not os.path.exists(os.path.dirname(dstpath)):
                    os.makedirs(os.path.dirname(dstpath))
                content = replace_template(file(srcpath).read(), var_values)
                file(dstpath, "w").write(content)

        # generate case spec
        spec_template = self.template["case_spec"]
        cmd_template = spec_template["cmd"]
        cmd = [replace_template(x, test_vector) for x in cmd_template]
        # support output_root in command binary
        binfile = replace_template(cmd[0], {"output_root": output_root})
        if os.path.isabs(binfile):
            binfile = os.path.relpath(binfile, case_path)
        if not os.path.exists(os.path.join(case_path, binfile)):
            raise ValueError("Command binary '%s' does not exists" % cmd[0])
        cmd[0] = binfile

        run_template = spec_template["run"]
        run = OrderedDict()
        for k in ["nnodes", "procs_per_node", "tasks_per_proc", "nprocs"]:
            v = replace_template(run_template[k], test_vector)
            v = safe_eval(v)
            run[k] = v
        rlt_template = spec_template["results"]
        results = [replace_template(x, test_vector) for x in rlt_template]
        envs_template = spec_template["envs"]
        envs = OrderedDict()
        for k, v in envs_template.iteritems():
            v = replace_template(v, test_vector)
            v = safe_eval(v)
            envs[k] = v
        case_spec = OrderedDict(zip(["cmd", "envs", "run", "results"],
                                    [cmd, envs, run, results]))

        # create empty output file, so when output file is used for special
        # signal, it's ready and will not be ignored.
        for f in case_spec["results"]:
            filepath = os.path.join(case_path, f)
            if not os.path.exists(filepath):
                file(filepath, "w").write("")

        return case_spec


class CustomCaseGenerator:

    def __init__(self, module, func, args):
        if not os.path.exists(module):
            raise RuntimeError("Module '%s' does not exists" % module)

        sys.path.insert(0, os.path.dirname(module))
        module_name = os.path.splitext(os.path.basename(module))[0]
        mod = importlib.import_module(module_name)
        fun = getattr(mod, func)
        if not hasattr(mod, func):
            raise RuntimeError("Can not find function '%s' in '%s'"
                               % (func, module))
        self.func = fun
        self.args = args

    def make_case(self, conf_root, output_root, case_path, test_vector):
        '''Generate a test case according to the specified test vector

        Args:
            conf_root (str): Absolute path containing the project config.
            output_root (str): Absolute path for the output root.
            case_path (str): Absolute path for the test case.
            test_vector (OrderedDict): Test case identification.

        Returns:
            dict: Test case specification

            Test case specification containing the following information to run
            a test case:

                {
                    "cmd": ["ls", "-l"]       # The command and its arguments
                    "envs": {"K": "V", ...}   # Environment variables to set
                    "results": ["STDOUT"]     # The result files to preserve
                    "run": {"nprocs": 1, ...} # The runner specific information
                }

        '''
        args = dict(self.args)
        args["conf_root"] = conf_root
        args["output_root"] = output_root
        args["case_path"] = case_path
        args["test_vector"] = test_vector
        case_spec = self.func(**args)

        # create empty output file, so when output file is used for special
        # signal, it's ready and will not be ignored.
        for f in case_spec["results"]:
            filepath = os.path.join(case_path, f)
            if not os.path.exists(filepath):
                file(filepath, "w").write("")

        return case_spec


class OutputOrganizer:

    def __init__(self, version=1):
        if version != 1:
            raise RuntimeError(
                "Unsupported output version '%s': only allow 1" %
                version)
        self.version = version

    def get_case_path(self, test_vector):
        segs = ["{0}-{1}".format(k, v) for k, v in test_vector.iteritems()]
        return os.path.join(*segs)

    def get_project_info_path(self):
        return "TestProject.json"

    def get_case_spec_path(self, test_vector):
        return os.path.join(self.get_case_path(test_vector), "TestCase.json")


class TestProjectBuilder:

    def __init__(self, conf_root):
        if not os.path.isabs(conf_root):
            conf_root = os.path.abspath(conf_root)
        self.conf_root = conf_root

        spec_file = os.path.join(self.conf_root, "TestProjectConfig.json")
        spec = parse_json(spec_file)

        # Do minimal sanity check
        project_version = spec.get("version", 1)
        if int(project_version) != 1:
            raise RuntimeError(
                "Unsupported project version '%s': only allow '1'" %
                project_version)

        # Setup basic project information
        project_info = spec["project"]
        self.name = project_info["name"]
        self.test_factors = project_info["test_factors"]
        data_files = project_info.get("data_files", [])
        self.data_files = data_files
        common_case_files = project_info.get("common_case_files", [])
        self.common_case_files = common_case_files

        # Build test vector generator
        test_vector_generator_name = project_info["test_vector_generator"]
        if test_vector_generator_name == "cart_product":
            args = spec["cart_product_vector_generator"]
            test_factor_values = args["test_factor_values"]
            self.test_vector_generator = CartProductVectorGenerator(
                self.test_factors,
                test_factor_values)
        elif test_vector_generator_name == "simple":
            args = spec["simple_vector_generator"]
            test_vectors = args["test_vectors"]
            self.test_vector_generator = SimpleVectorGenerator(
                self.test_factors,
                test_vectors)
        else:
            raise RuntimeError(
                "Unknown test vector generator '%s'" %
                test_vector_generator_name)

        # Build test case generator
        test_case_generator_name = project_info["test_case_generator"]
        if test_case_generator_name == "custom":
            info = spec["custom_case_generator"]
            module = info["import"]
            if not os.path.isabs(module):
                module = os.path.normpath(os.path.join(self.conf_root, module))
            func = info["func"]
            args = info.get("args", {})
            self.test_case_generator = CustomCaseGenerator(module, func, args)
        elif test_case_generator_name == "template":
            template = spec["template_case_generator"]
            self.test_case_generator = TemplateCaseGenerator(template)
        else:
            raise RuntimeError(
                "Unknown test case generator '%s'" %
                test_case_generator_name)

        # Build output organizer
        self.output_organizer = OutputOrganizer(version=1)

    def write(self, output_root, link_files=False):
        # Prepare directories
        if not os.path.isabs(output_root):
            output_root = os.path.abspath(output_root)
        if not os.path.exists(output_root):
            os.makedirs(output_root)

        # Handle data files: leave absolute path as-is, copy or link relative
        # path to the output directory
        for path in self.data_files:
            if os.path.isabs(path):
                continue
            srcpath = os.path.join(self.conf_root, path)
            dstpath = os.path.join(output_root, path)
            if not os.path.exists(srcpath):
                raise RuntimeError(
                    "Data file specified but not found: '%s'" % path)
            if os.path.isdir(srcpath):
                dstdir = os.path.dirname(dstpath)
                if not os.path.exists(dstdir):
                    os.makedirs(dstdir)
                if os.path.exists(dstpath):
                    if os.path.islink(dstpath):
                        os.remove(dstpath)
                    elif os.path.isdir(dstpath):
                        shutil.rmtree(dstpath)
                    else:
                        os.remove(dstpath)
                if link_files:
                    os.symlink(srcpath, dstpath)
                else:
                    shutil.copytree(srcpath, dstpath)
            elif os.path.isfile(srcpath):
                dstdir = os.path.dirname(dstpath)
                if not os.path.exists(dstdir):
                    os.makedirs(dstdir)
                if os.path.exists(dstpath):
                    if os.path.islink(dstpath):
                        os.remove(dstpath)
                    elif os.path.isdir(dstpath):
                        shutil.rmtree(dstpath)
                    else:
                        os.remove(dstpath)
                if link_files:
                    os.symlink(srcpath, dstpath)
                else:
                    shutil.copyfile(srcpath, dstpath)
                    shutil.copystat(srcpath, dstpath)
            else:
                raise RuntimeError("File type not supported: '%s'" % path)

        # Generate test cases and write test case config
        for case in self.test_vector_generator.iteritems():
            case_path = self.output_organizer.get_case_path(case)
            case_fullpath = os.path.join(output_root, case_path)
            if not os.path.exists(case_fullpath):
                os.makedirs(case_fullpath)

            # copy common case files to case path, only ordinary file is, each
            # file is copied to the case path, without reconstructing the dir.
            for path in self.common_case_files:
                srcpath = path
                if not os.path.isabs(path):
                    srcpath = os.path.join(self.conf_root, path)
                if not os.path.isfile(srcpath):
                    raise ValueError(
                        "Common case file '%s' is not a file." % path)
                if not os.path.exists(srcpath):
                    raise ValueError("Common case file '%s' not found" % path)
                dstpath = os.path.join(case_fullpath, os.path.basename(path))
                if os.path.exists(dstpath):
                    os.remove(dstpath)
                shutil.copyfile(srcpath, dstpath)

            cwd = os.path.abspath(os.getcwd())
            os.chdir(case_fullpath)
            try:
                case_spec = self.test_case_generator.make_case(
                    self.conf_root,
                    output_root,
                    case_fullpath,
                    case)
            finally:
                os.chdir(cwd)

            case_spec_path = self.output_organizer.get_case_spec_path(case)
            case_spec_fullpath = os.path.join(output_root, case_spec_path)
            json.dump(case_spec, file(case_spec_fullpath, "w"), indent=2)

        # Write project config
        info = [("version", 1), ("name", self.name),
                ("test_factors", self.test_factors)]
        info = OrderedDict(info)
        info["data_files"] = self.data_files
        test_defs = []
        for case in self.test_vector_generator.iteritems():
            vector = case.values()
            path = self.output_organizer.get_case_path(case)
            test_defs.append(OrderedDict(
                zip(["test_vector", "path"], [vector, path])))
        info["test_cases"] = test_defs
        project_info_path = self.output_organizer.get_project_info_path()
        project_info_fullpath = os.path.join(output_root, project_info_path)
        json.dump(info, file(project_info_fullpath, "w"), indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("conf_root", help="Project configuration directory")
    parser.add_argument("output_root", help="Output directory")
    parser.add_argument("--link-files", action="store_true",
                        help="Sympolic link data files instead of copy")

    config = parser.parse_args()
    project = TestProjectBuilder(config.conf_root)
    project.write(config.output_root, config.link_files)


if __name__ == "__main__":
    main()
