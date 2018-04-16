set(CEPH_DISK_VIRTUALENV ${CEPH_BUILD_VIRTUALENV}/ceph-disk-virtualenv)

if(WITH_PYTHON3)
  set(CEPH_DISK_PYTHON_BINARY python3)
else()
  set(CEPH_DISK_PYTHON_BINARY python2.7)
endif()

add_custom_target(ceph-disk
  COMMAND
  ${CMAKE_SOURCE_DIR}/src/tools/setup-virtualenv.sh --python=${CEPH_DISK_PYTHON_BINARY} ${CEPH_DISK_VIRTUALENV} &&
  ${CEPH_DISK_VIRTUALENV}/bin/pip install --no-index --find-links=file:${CMAKE_SOURCE_DIR}/src/ceph-disk/wheelhouse -e .
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/src/ceph-disk
  COMMENT "ceph-disk is being created")
add_dependencies(tests ceph-disk)

include(Distutils)
distutils_install_module(ceph_disk
  INSTALL_SCRIPT ${CMAKE_INSTALL_FULL_SBINDIR})
