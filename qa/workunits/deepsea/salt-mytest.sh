#!/bin/bash -ex
sudo systemctl status salt-master
sudo salt '*' test.ping
echo "All good"
