#!/bin/bash
# Provision el10-inventory: AlmaLinux 10 with nginx only. Exercises Python 3.12
# targets and the inventory profile on the newest RHEL major.
set -euo pipefail

dnf install -y nginx
dnf makecache

echo "el10-inventory provisioning complete"
