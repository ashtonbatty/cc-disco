#!/bin/bash
# Provision el7-webserver scenario: feature-rich CentOS 7 with httpd, nginx,
# firewalld, sssd/krb5, agents, cron jobs, and hardened configs.
set -euo pipefail

FILES=/tmp/provision-files

# --- Packages ---
yum install -y \
    httpd nginx firewalld \
    sssd krb5-workstation \
    cronie \
    net-tools \
    && yum clean all

# --- SSSD / Kerberos ---
cp "$FILES/sssd.conf" /etc/sssd/sssd.conf
chmod 600 /etc/sssd/sssd.conf
cp "$FILES/krb5.conf" /etc/krb5.conf
touch /etc/krb5.keytab
cp "$FILES/nsswitch.conf" /etc/nsswitch.conf

# --- Sudoers ---
cp "$FILES/sudoers-admins" /etc/sudoers.d/admins
chmod 0440 /etc/sudoers.d/admins

# --- SSH hardening ---
cp "$FILES/sshd_config" /etc/ssh/sshd_config

# --- SELinux config (enforcement not possible in container) ---
cp "$FILES/selinux-config" /etc/selinux/config

# --- GRUB defaults ---
mkdir -p /etc/default
cp "$FILES/grub" /etc/default/grub

# --- fstab with NFS mount ---
cp "$FILES/fstab" /etc/fstab

# --- Cron ---
echo "0 2 * * * root /usr/local/bin/backup.sh" > /etc/cron.d/backup-job

# --- Agent directories (for backup/monitoring detection) ---
mkdir -p /opt/splunkforwarder/bin
mkdir -p /opt/CrowdStrike/falconctl

# --- Enable services (systemd) ---
systemctl enable firewalld httpd sshd crond 2>/dev/null || true

echo "el7-webserver provisioning complete"
