#!/bin/sh -ex

CLIENTNODE=$1
POOLNAME=$2
IMAGE=$3
IMG_SIZE='1024M'
NEW_IMAGE_SIZE='2048M'

client_preparation() {
    'qemu-block-rbd','qemu-tools' # these should be listed in packages.yaml?
}

test_qemu() {
    ## should we clean via remove_images as in https://github.com/ceph/ceph/blob/b2f6d526cde551f1dce355d7516df449f78b18c1/qa/workunits/rbd/cli_generic.sh#L13 ?
    echo "testing QEMU image operations..."
    # no for loops - use just one combination
    ssh $CLIENTNODE qemu-img create -f raw rbd:$POOLNAME/$IMAGE $IMG_SIZE
    ssh $CLIENTNODE qemu-img info rbd:$POOLNAME/$IMAGE
    ssh $CLIENTNODE qemu-img resize rbd:$POOLNAME/$IMAGE $NEW_IMAGE_SIZE
    ssh $CLIENTNODE qemu-img info rbd:$POOLNAME/$IMAGE | sed -n '3p' | grep -q $NEW_IMAGE_SIZE && exit 0

    # Do we need to do qemu-img convert ?
    # https://docs.openstack.org/image-guide/convert-images.html
    #validate format after conversion ?
    ssh $CLIENTNODE qemu-img info rbd:$POOLNAME/$IMAGE | sed -n '2p'
}


# def test_qemu():
# #    global vErrors
# #    try:
#         delete_all_images()
#         create_qemu_image()
#         validate_qemu_image_presence()
#         resize_qemu_image()
#         validate_qemu_image_size()
#         # convert_qemu_image() # missing physical image on machine
#         # validate_qemu_image_format() depends on function above
# #    except:
# #        sError = str(sys.exc_info()[0])+" : "+str(sys.exc_info()[1])
# #        log.error(inspect.stack()[0][3] + "Failed with error - "+sError)
# #        vErrors.append(sError)
# #        raise sys.exc_info()[0], sys.exc_info()[1]

# ###Maybe we can skip delete_all_images this since we always start with clean cluster?
# def delete_all_images(): 
#     rbd_operations.delete_exported_images()
#             cmd = "ssh %s sudo rm -f im* || true" % os.environ["CLIENTNODE"]
#     for pool in rbd_operations.get_pool_names():
#         for image in rbd_operations.images_in_pool(pool):
#             rbd_operations.remove_image(pool, image)
#                 cmd = "ssh %s rbd -p %s rm %s" % (os.environ["CLIENTNODE"], pool, image)

#     do we also need to export images?
#         def export_image(dictImg):
#             # export image to file
#             name = dictImg.get('name', None)
#             pool = dictImg.get('pool', 'rbd')
#             exported_image_name = name+"_exported"
#             cmd = "ssh %s rbd -p %s export %s %s" % (os.environ["CLIENTNODE"], pool, name, exported_image_name)

# def create_qemu_image():
#     for image in yaml_data['qemu']:
#         rbd_operations.create_qemu_image(image)
#             cmd = "ssh %s qemu-img create -f %s rbd:%s/%s %s" % (os.environ["CLIENTNODE"], format='raw', poolname, imagename, size)

# def validate_qemu_image_presence():
#     for image in yaml_data['qemu']:
#         rbd_operations.validate_qemu_image_presence(image)
#             cmd = "ssh %s qemu-img info rbd:%s/%s" % (os.environ["CLIENTNODE"], poolname, imagename)

# def resize_qemu_image():
#     for image in yaml_data['qemu']:
#         # Optional parameters are: size
#         # Default value = 2000
#         rbd_operations.resize_qemu_image(image)
#             cmd = "ssh %s qemu-img resize rbd:%s/%s %s" % \
#           (os.environ["CLIENTNODE"], poolname, imagename, size)

# def validate_qemu_image_size():
#     for image in yaml_data['qemu']:
#         rbd_operations.validate_qemu_image_size(image)
#             cmd = "ssh %s qemu-img info rbd:%s/%s | sed -n '3p'" % (os.environ["CLIENTNODE"], poolname, imagename)

# # convert_qemu_image() # missing physical image on machine
# #  physical_image = []  # TODO
#     cmd = "ssh %s qemu-img convert -f %s -O %s %s rbd:%s/%s" % \
#           (os.environ["CLIENTNODE"], from_format, to_format, physical_image, poolname, imagename)

# test_rbd.yaml:

#     workingdir: /home/jenkins/cephdeploy-cluster
#     clientnode:
#     - teuthida-10
#     allnodes:
#     - teuthida-10
#     - teuthida-4
#     - teuthida-2
#     - teuthida-1
#     initmons:
#     - teuthida-4
#     - teuthida-2
#     - teuthida-1
#     osd_zap:
#     - teuthida-4:sdb
#     - teuthida-2:sdb
#     - teuthida-1:sdb
#     osd_prepare:
#     - teuthida-4:sdb
#     - teuthida-2:sdb
#     - teuthida-1:sdb
#     osd_activate:
#     - teuthida-4:sdb1
#     - teuthida-2:sdb1
#     - teuthida-1:sdb1
#     default_pgs: 192
#     images:
#     - {name: im1_rbd, size: 1024, pool: rbd}
#     - {name: im2_rbd, size: 1024, pool: rbd}
#     - {name: im3_rbd, size: 512, pool: rbd}
#     radosobjects:
#     - {objname: test-obj-1_rbd, pool: rbd}
#     createpools:
#     - {poolname: test-pool-1_rbd, pg-num: 64, size: 2}
#     - {poolname: data, pg-num: 64, size: 2}
#     - {poolname: metadata, pg-num: 64, size: 2}
#     librbd_images:
#     - {poolname: rbd, imagename: librbdimg, size_mb: 300}
#     snapshots:
#     - { pool: rbd, snapname: snap, name: im1_rbd}
#     qemu:
#     - { pool: rbd, name: qemu1, size: 1000}
#     - { pool: rbd, name: qemu2, size: 500}
#     rgws:
#     - {rgw-host: host-44-0-3-216, rgw-name: gateway1, rgw-port: 7480}



# setup needs install packages on the client:
#     for pkg in ['qemu-block-rbd','qemu-tools']:
#         zypperutils.installPkg(pkg, os.environ["CLIENTNODE"])
