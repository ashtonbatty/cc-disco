#!/bin/bash
# Provision el9-extended: AlmaLinux 9 with nginx (OS vendor), htop from EPEL
# (third-party vendor), a versionlock on nginx and the authselect "minimal"
# profile with one feature. The dnf cache is kept for the playbook's
# cache-only queries.
set -euo pipefail

dnf install -y epel-release
dnf install -y nginx htop python3-dnf-plugin-versionlock
dnf versionlock add nginx
dnf install -y authselect
authselect select minimal with-mkhomedir --force
dnf makecache

echo "el9-extended provisioning complete"
