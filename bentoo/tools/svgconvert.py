#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
'''
svgconvert - Simple tool to convert svg to pdf and png

This tool converts svg to pdf and png using phantomjs. It handles mising fonts
correctly, so svgs with unicode text objects are handled gracefuly.
'''

import argparse
import os
import subprocess
import xml.etree.ElementTree

rasterize_js = '''
"use strict";
var page = require('webpage').create(),
    system = require('system'),
    address, output, size, pageWidth, pageHeight;

address = system.args[1];
output = system.args[2];
page.viewportSize = { width: 600, height: 600 };
if (system.args.length > 3 && system.args[2].substr(-4) === ".pdf") {
    size = system.args[3].split('*');
    page.paperSize = size.length === 2 ? { width: size[0], height: size[1],
                                           margin: '0px' }
                                        : { format: system.args[3],
                                            orientation: 'portrait',
                                            margin: '1cm' };
} else if (system.args.length > 3 && system.args[3].substr(-2) === "px") {
    size = system.args[3].split('*');
    if (size.length === 2) {
        pageWidth = parseInt(size[0], 10);
        pageHeight = parseInt(size[1], 10);
        page.viewportSize = { width: pageWidth, height: pageHeight };
        page.clipRect = { top: 0, left: 0,
                          width: pageWidth, height: pageHeight };
    } else {
        pageWidth = parseInt(system.args[3], 10);
        pageHeight = parseInt(pageWidth * 3/4, 10);
        page.viewportSize = { width: pageWidth, height: pageHeight };
    }
}
if (system.args.length > 4) {
    page.zoomFactor = system.args[4];
}
page.open(address, function (status) {
    if (status !== 'success') {
        console.log('Unable to load the address!');
        phantom.exit(1);
    } else {
        window.setTimeout(function () {
            page.render(output);
            phantom.exit();
        }, 200);
    }
});
'''


def svgconvert(svgfile, outfile):
    svg = xml.etree.ElementTree.parse(svgfile)
    root = svg.getroot()
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    width = root.attrib["width"]
    height = root.attrib["height"]
    rasterize_fn = os.path.join("/tmp", "svgconvert-%d.js" % os.getpid())
    file(rasterize_fn, "w").write(rasterize_js)
    try:
        cmd = ["phantomjs", rasterize_fn, svgfile, outfile,
               "%s*%s" % (width, height)]
        subprocess.check_call(cmd, shell=False)
    finally:
        os.remove(rasterize_fn)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("svgfile",
                        help="SVG file to convert")
    parser.add_argument("outfile",
                        help="Output file")

    args = parser.parse_args()
    svgconvert(args.svgfile, args.outfile)

if __name__ == "__main__":
    main()
