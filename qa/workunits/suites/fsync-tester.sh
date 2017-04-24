#!/bin/sh -x

#
# SUSE-specific hack to install lsof from OBS (begin)
#
source /etc/os-release
[ "x${ID}x" = "xslesx" ] && [ "x${VERSION_ID}x" = "x12.1x" ] && suse_version="42.1"
[ "x${ID}x" = "xopensusex" ] && [ "x${VERSION_ID}x" = "x42.1x" ] && suse_version="42.1"
[ "x${ID}x" = "xslesx" ] && [ "x${VERSION_ID}x" = "x12.2x" ] && suse_version="42.2"
[ "x${ID}x" = "xopensusex" ] && [ "x${VERSION_ID}x" = "x42.2x" ] && suse_version="42.2"
[ "x${ID}x" = "xslesx" ] && [ "x${VERSION_ID}x" = "x12.3x" ] && suse_version="42.3"
[ "x${ID}x" = "xopensusex" ] && [ "x${VERSION_ID}x" = "x42.3x" ] && suse_version="42.3"
if [ ! -z "$suse_version" ] ; then
    sudo zypper --non-interactive addrepo http://download.opensuse.org/repositories/utilities/openSUSE_Leap_${suse_version}/utilities.repo
    sudo zypper --gpg-auto-import-keys ref
    sudo zypper --non-interactive install lsof
fi
#
# SUSE-specific hack to install lsof from OBS (end)
#

set -e

wget http://download.ceph.com/qa/fsync-tester.c
gcc fsync-tester.c -o fsync-tester

./fsync-tester

echo $PATH
whereis lsof
lsof
