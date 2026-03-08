#!/bin/bash
# Provision el7-minimal scenario: bare CentOS 7 with no extra packages.
# iptables-services enabled, firewalld absent.
set -euo pipefail

# --- Packages ---
yum install -y iptables-services && yum clean all

# Remove firewalld if present
yum remove -y firewalld 2>/dev/null || true

# --- Enable iptables, disable firewalld ---
systemctl enable iptables 2>/dev/null || true

# --- Minimal fstab ---
cat > /etc/fstab <<'EOF'
/dev/mapper/centos-root /                       xfs     defaults        0 0
/dev/mapper/centos-swap swap                    swap    defaults        0 0
EOF

# No sssd, no krb5, no sudoers.d entries, no cron jobs, no agent dirs

echo "el7-minimal provisioning complete"
