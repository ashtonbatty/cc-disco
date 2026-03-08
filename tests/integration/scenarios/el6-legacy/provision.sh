#!/bin/bash
# Provision el6-legacy scenario: CentOS 6 with sysvinit, xinetd, ntp,
# legacy networking, and deprecated packages.
set -euo pipefail

FILES=/tmp/provision-files

# --- Packages ---
yum install -y \
    xinetd ntp iptables cronie net-tools \
    && yum clean all

# --- xinetd config ---
cp "$FILES/tftp-xinetd" /etc/xinetd.d/tftp

# --- NTP config ---
cp "$FILES/ntp.conf" /etc/ntp.conf

# --- Legacy network config ---
cp "$FILES/ifcfg-eth0" /etc/sysconfig/network-scripts/ifcfg-eth0

# --- fstab with ext3 ---
cp "$FILES/fstab" /etc/fstab

# --- Enable services via chkconfig (sysvinit) ---
chkconfig iptables on 2>/dev/null || true
chkconfig xinetd on 2>/dev/null || true
chkconfig ntpd on 2>/dev/null || true
chkconfig crond on 2>/dev/null || true

echo "el6-legacy provisioning complete"
