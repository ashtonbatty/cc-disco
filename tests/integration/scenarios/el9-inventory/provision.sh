#!/bin/bash
# Provision el9-inventory: AlmaLinux 9 with nginx (OS vendor), htop from EPEL
# (third-party vendor) and a versionlock on nginx. The dnf cache is kept for
# the playbook's cache-only queries.
set -euo pipefail

dnf install -y epel-release
dnf install -y nginx htop python3-dnf-plugin-versionlock
dnf versionlock add nginx
dnf makecache

echo "el9-inventory provisioning complete"
