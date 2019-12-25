# coding: utf-8

from __future__ import division, print_function, unicode_literals

import argparse
import importlib
import itertools
import json
import os
import re
import shutil
import string
import sys
from collections import OrderedDict

from bentoo.common.conf import load_conf
from bentoo.common.utils import replace_template, safe_eval


class SimpleVectorGenerator(object):
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

    def items(self):
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


class CartProductVectorGenerator(object):
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

    def items(self):
        '''An iterator over the range of test vectors

        Yields:
            OrderedDict: a test vector.

            OrderedDict.values() is the test factor values and
            OrderedDict.keys() is the test factor names.

        '''
        factor_values = [self.factor_values[k] for k in self.test_factors]
        for v in itertools.product(*factor_values):
            yield OrderedDict(zip(self.test_factors, v))


class CustomVectorGenerator(object):
    '''Custom test vector generator

    Generate a collection of test vectors by calling a user defined function,
    which returns a list of test vectors.

    Args:
        test_factors (list): test factor names.
        spec (dict): generator definition.

    '''
    def __init__(self, test_factors, spec, project_root):
        self.test_factors = test_factors

        module = spec["import"]
        if not os.path.isabs(module):
            module = os.path.abspath(os.path.join(project_root, module))
        func = spec["func"]
        args = spec.get("args", {})
        if not os.path.exists(module):
            raise RuntimeError("Module '%s' does not exists" % module)

        module_path = os.path.dirname(module)
        if module_path not in sys.path:
            sys.path.insert(0, module_path)
        module_name = os.path.splitext(os.path.basename(module))[0]
        mod = importlib.import_module(module_name)
        if not hasattr(mod, func):
            raise RuntimeError("Can not find function '%s' in '%s'" %
                               (func, module))
        fun = getattr(mod, func)
        real_args = dict(args)
        real_args["conf_root"] = os.path.abspath(project_root)
        real_args["test_factors"] = self.test_factors
        self.test_vectors = fun(**real_args)

    def items(self):
        '''An iterator over the range of test vectors

        Yields:
            OrderedDict: a test vector.

            OrderedDict.values() is the test factor values and
            OrderedDict.keys() is the test factor names.

        '''
        for v in self.test_vectors:
            yield OrderedDict(zip(self.test_factors, v))




class TemplateCaseGenerator(object):
    def __init__(self, template):
        assert ("case_spec" in template)
        self.template = template.copy()
        if "copy_files" not in self.template:
            self.template["copy_files"] = OrderedDict()
        if "link_files" not in self.template:
            self.template["link_files"] = OrderedDict()
        if "inst_templates" not in self.template:
            self.template["inst_templates"] = OrderedDict()

    def make_case(self, conf_root, output_root, case_path, test_vector):
        '''Generate a test case according to the specified test vector'''
        template_vars = dict(test_vector)
        template_vars["conf_root"] = conf_root
        template_vars["output_root"] = output_root
        template_vars["case_path"] = case_path
        # copy case files: each file is defiend as (src, dst), where src is
        # relative to conf_root and dst is relative to case_path.
        for src, dst in self.template["copy_files"].items():
            srcpath = replace_template(src, template_vars)
            dstpath = replace_template(dst, template_vars)
            if not os.path.isabs(srcpath):
                srcpath = os.path.join(conf_root, srcpath)
            if not os.path.isabs(dstpath):
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

        # link case files: each file is defiend as (src, dst), where src is
        # relative to output_root and dst is relative to case_path.
        for src, dst in self.template["link_files"].items():
            srcpath = replace_template(src, template_vars)
            dstpath = replace_template(dst, template_vars)
            if not os.path.isabs(srcpath):
                srcpath = os.path.join(output_root, srcpath)
            if not os.path.isabs(dstpath):
                dstpath = os.path.join(case_path, dstpath)
            if os.path.exists(dstpath):
                if os.path.isdir(dstpath):
                    shutil.rmtree(dstpath)
                else:
                    os.remove(dstpath)
            if not os.path.exists(srcpath):
                raise ValueError("Case file '%s' not found" % srcpath)
            srcpath = os.path.relpath(srcpath, case_path)
            if not os.path.exists(os.path.dirname(dstpath)):
                os.makedirs(os.path.dirname(dstpath))
            if os.path.exists(dstpath):
                os.remove(dstpath)
            os.symlink(srcpath, dstpath)

        # instantiate template files based on template substitution
        inst_tpls = self.template["inst_templates"]
        if inst_tpls:
            var_values = {}
            for k, v in inst_tpls["variables"].items():
                v = replace_template(v, template_vars)
                v = safe_eval(v)
                var_values[k] = v
            for src, dst in inst_tpls["templates"].items():
                srcpath = replace_template(src, template_vars)
                dstpath = replace_template(dst, template_vars)
                if not os.path.isabs(srcpath):
                    srcpath = os.path.join(conf_root, srcpath)
                if not os.path.isabs(dstpath):
                    dstpath = os.path.join(case_path, dstpath)
                if not os.path.exists(srcpath):
                    raise ValueError("Template '%s' does not exist" % srcpath)
                if not os.path.isfile(srcpath):
                    raise ValueError("Template '%s' is not a file" % srcpath)
                if os.path.exists(dstpath):
                    os.remove(dstpath)
                if not os.path.exists(os.path.dirname(dstpath)):
                    os.makedirs(os.path.dirname(dstpath))
                content = replace_template(open(srcpath).read(), var_values)
                open(dstpath, "w").write(content)

        # generate case spec
        spec_template = self.template["case_spec"]
        cmd_template = spec_template["cmd"]
        cmd = [replace_template(x, template_vars) for x in cmd_template]

        def transform_path(x):
            x = replace_template(x, {"output_root": output_root})
            if os.path.isabs(x) and x.startswith(output_root):
                x = os.path.relpath(x, case_path)
            p = x if os.path.isabs(x) else os.path.join(x, case_path)
            return x if os.path.exists(p) else None

        # support output_root in command binary
        for i, item in enumerate(cmd):
            v = transform_path(item)
            if v is not None:
                cmd[i] = v
            elif i == 0:
                raise ValueError("Command binary '%s' does not exists" %
                                 cmd[0])

        run_template = spec_template["run"]
        run = OrderedDict()
        for k in ["nnodes", "procs_per_node", "tasks_per_proc", "nprocs"]:
            v = replace_template(run_template[k], template_vars)
            v = safe_eval(v)
            run[k] = v
        rlt_template = spec_template.get("results", [])
        results = [replace_template(x, template_vars) for x in rlt_template]
        envs_template = spec_template.get("envs", {})
        envs = OrderedDict()
        for k, v in envs_template.items():
            v = replace_template(v, template_vars)
            v = safe_eval(v)
            envs[k] = v
        validator = OrderedDict()
        validator_template = spec_template.get("validator", None)
        if validator_template:
            exists_tpl = validator_template.get("exists", [])
            if exists_tpl:
                v = [replace_template(x, template_vars) for x in exists_tpl]
                validator["exists"] = v
            contains_tpl = validator_template.get("contains", {})
            if contains_tpl:
                contains = OrderedDict()
                for k, v in contains_tpl.items():
                    k = replace_template(k, template_vars)
                    v = replace_template(v, template_vars)
                    contains[k] = v
                validator["contains"] = contains
        case_spec = OrderedDict(
            zip(["cmd", "envs", "run", "results", "validator"],
                [cmd, envs, run, results, validator]))

        # create empty output file, so when output file is used for special
        # signal, it's ready and will not be ignored.
        for f in case_spec["results"]:
            filepath = os.path.join(case_path, f)
            if not os.path.exists(filepath):
                open(filepath, "w").write("")

        return case_spec


class CustomCaseGenerator(object):
    def __init__(self, module, func, args):
        if not os.path.exists(module):
            raise RuntimeError("Module '%s' does not exists" % module)

        sys.path.insert(0, os.path.abspath(os.path.dirname(module)))
        module_name = os.path.splitext(os.path.basename(module))[0]
        mod = importlib.import_module(module_name)
        if not hasattr(mod, func):
            raise RuntimeError("Can not find function '%s' in '%s'" %
                               (func, module))
        fun = getattr(mod, func)

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
                    "validator": {"exists": [...], ..} # The result validator
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
                open(filepath, "w").write("")

        return case_spec


def identifier(value):
    '''Create a valid identifier out of a value'''
    a = re.sub(r"\W", "_", repr(value).strip().lower())
    return re.sub(r"_+", "_", a)


class OutputOrganizer(object):
    def __init__(self, version=1):
        if version != 1:
            raise RuntimeError(
                "Unsupported output version '%s': only allow 1" % version)
        self.version = version

    def get_case_path(self, test_vector):
        segs = [
            "{0}-{1}".format(identifier(k), identifier(v))
            for k, v in test_vector.items()
        ]
        return os.path.join(*segs)

    def get_project_info_path(self):
        return "TestProject.json"

    def get_case_spec_path(self, test_vector):
        return os.path.join(self.get_case_path(test_vector), "TestCase.json")


class TestProjectBuilder(object):
    def __init__(self, conf_root):
        if not os.path.isabs(conf_root):
            conf_root = os.path.abspath(conf_root)
        self.conf_root = conf_root

        spec_file = os.path.join(self.conf_root, "TestProjectConfig.json")
        if not os.path.exists(spec_file):
            spec_file = os.path.join(self.conf_root, "TestProjectConfig.yml")
        if not os.path.exists(spec_file):
            raise RuntimeError(
                ("Either TestProjectConfig.json or " +
                 "TestProjectConfig.yml shall exists under {}").format(
                     self.conf_root))
        spec = load_conf(spec_file)

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
                self.test_factors, test_factor_values)
        elif test_vector_generator_name == "simple":
            args = spec["simple_vector_generator"]
            test_vectors = args["test_vectors"]
            self.test_vector_generator = SimpleVectorGenerator(
                self.test_factors, test_vectors)
        elif test_vector_generator_name == "custom":
            args = spec["custom_vector_generator"]
            self.test_vector_generator = CustomVectorGenerator(
                self.test_factors, args, conf_root)
        else:
            raise RuntimeError("Unknown test vector generator '%s'" %
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
            raise RuntimeError("Unknown test case generator '%s'" %
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
                raise RuntimeError("Data file specified but not found: '%s'" %
                                   path)
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
        for case in self.test_vector_generator.items():
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
                    raise ValueError("Common case file '%s' is not a file." %
                                     path)
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
                    self.conf_root, output_root, case_fullpath, case)
            finally:
                os.chdir(cwd)

            case_spec_path = self.output_organizer.get_case_spec_path(case)
            case_spec_fullpath = os.path.join(output_root, case_spec_path)
            json.dump(case_spec, open(case_spec_fullpath, "w"), indent=2)

        # Write project config
        info = [("version", 1), ("name", self.name),
                ("test_factors", self.test_factors)]
        info = OrderedDict(info)
        info["data_files"] = self.data_files
        test_defs = []
        for case in self.test_vector_generator.items():
            vector = list(case.values())
            path = self.output_organizer.get_case_path(case)
            test_defs.append(
                OrderedDict(zip(["test_vector", "path"], [vector, path])))
        info["test_cases"] = test_defs
        project_info_path = self.output_organizer.get_project_info_path()
        project_info_fullpath = os.path.join(output_root, project_info_path)
        json.dump(info, open(project_info_fullpath, "w"), indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("conf_root", help="Project configuration directory")
    parser.add_argument("output_root", help="Output directory")
    parser.add_argument("--link-files",
                        action="store_true",
                        help="Sympolic link data files instead of copy")

    config = parser.parse_args()
    project = TestProjectBuilder(config.conf_root)
    project.write(config.output_root, config.link_files)


if __name__ == "__main__":
    main()
