#!/bin/bash
#

function get_version() {
    tag=$(git describe --tags $1)
    echo ${tag#v}
}

if [ $# -eq 0 ]; then
    REVISION=HEAD
else
    REVISION=$1
fi

version=$(get_version $REVISION)
tarball_prefix="bentoo-$version"
git archive $REVISION --prefix="$tarball_prefix"/ -o "$tarball_prefix.tar.gz"
