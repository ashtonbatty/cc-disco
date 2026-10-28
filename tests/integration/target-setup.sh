#!/bin/bash
# Common setup for every integration target: the ansible user with passwordless
# sudo, key-only sshd, and the controller's public key. Each Containerfile
# installs openssh-server, sudo and python first, then runs this.
#   $1: the controller's public key
set -euo pipefail

useradd -m -s /bin/bash ansible
echo "ansible ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/ansible
chmod 0440 /etc/sudoers.d/ansible

# Host keys. OpenSSH 5.3 (CentOS 6) has no -A: generate ECDSA first, matching
# production RHEL 6.5+ hosts, since modern clients reject SHA-1 ssh-rsa host keys.
if ! ssh-keygen -A 2>/dev/null; then
    ssh-keygen -q -t ecdsa -b 256 -f /etc/ssh/ssh_host_ecdsa_key -N ""
    ssh-keygen -q -t rsa -f /etc/ssh/ssh_host_rsa_key -N ""
    printf 'HostKey /etc/ssh/ssh_host_ecdsa_key\nHostKey /etc/ssh/ssh_host_rsa_key\n' >> /etc/ssh/sshd_config
fi

sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#*PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#*UsePAM.*/UsePAM yes/' /etc/ssh/sshd_config
# pam_loginuid fails in containers, so make it optional.
sed -i 's/^\(session.*pam_loginuid.so\)$/session optional pam_loginuid.so/' /etc/pam.d/sshd
mkdir -p /run/sshd

install -d -m 700 -o ansible -g ansible /home/ansible/.ssh
install -m 600 -o ansible -g ansible "$1" /home/ansible/.ssh/authorized_keys
