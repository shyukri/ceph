#!/bin/bash -ex

POOL_NAME="rbd"  # using one from create_all_pools_at_once
IMAGE_NAME="image-$$"
IMAGE_SIZE="1024"  # MB
SNAP_NAME="rbd_snap"
TARGET_DIR="snap-test"

function setup() {
    rbd create ${POOL_NAME}/${IMAGE_NAME} --size=${IMAGE_SIZE}
    rbd snap create ${POOL_NAME}/${IMAGE_NAME}@${SNAP_NAME}
}

function test() {
    # No diff in the beginning
    # rbd diff has exit code 0 in both cases, so check is against the command output
    [[ -z "$(rbd diff ${POOL_NAME}/${IMAGE_NAME})" ]] && echo "No diff as expected"
    rbd snap ls ${POOL_NAME}/${IMAGE_NAME} | grep ${SNAP_NAME}
    rbd info ${POOL_NAME}/${IMAGE_NAME}
    # By default we have: features: layering, exclusive-lock, object-map, fast-diff, deep-flatten
    # so object-map fast-diff deep-flatten need to be disabled, otherwise rbd map fails
    rbd feature disable ${POOL_NAME}/${IMAGE_NAME} object-map fast-diff deep-flatten
    DEVICE="$(sudo rbd map ${POOL_NAME}/${IMAGE_NAME})" # /dev/rbdX
    # Mkfs, Mount, write to mounted image
    sudo mkfs.xfs "${DEVICE}"
    sudo mkdir ${TARGET_DIR} || true
    sudo mount "${DEVICE}" "${TARGET_DIR}"
    sudo chown -R ubuntu:users ${TARGET_DIR}
    touch ${TARGET_DIR}/testfile.txt && echo "content" > ${TARGET_DIR}/testfile.txt
    # Validate diff after write
    [[ -n "$(rbd diff ${POOL_NAME}/${IMAGE_NAME})" ]] && echo "has diff as expected"
    rbd status ${POOL_NAME}/${IMAGE_NAME} || rbd showmapped
    sudo umount ${TARGET_DIR} || sudo dmesg | tail
    sudo rbd unmap "${DEVICE}" || sudo fuser -amv "${DEVICE}"
    rbd snap rollback ${POOL_NAME}/${IMAGE_NAME}@${SNAP_NAME}
    [[ -z "$(rbd diff ${POOL_NAME}/${IMAGE_NAME})" ]] && echo "No diff after rollback"
}

function teardown() {
    rbd snap purge ${POOL_NAME}/${IMAGE_NAME}
    rbd snap ls ${POOL_NAME}/${IMAGE_NAME}
    rbd -p ${POOL_NAME} rm ${IMAGE_NAME}
}

#### Start

setup
test
teardown
echo "RBD Snapshot test ran OK"