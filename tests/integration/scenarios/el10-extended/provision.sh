#!/bin/bash
# Provision el10-extended: AlmaLinux 10 with nginx and authselect (installing it
# selects the "local" profile). Exercises Python 3.12 targets and the extended
# profile on the newest RHEL major.
set -euo pipefail

dnf install -y nginx authselect
dnf makecache

echo "el10-extended provisioning complete"
