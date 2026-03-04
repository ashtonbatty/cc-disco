# cc-disco — RHEL Server Discovery Playbook

Ansible playbook to gather server facts from RHEL 6/7/8 hosts for upgrade/modernisation planning to RHEL 9/10. Outputs a single YAML report organised by hostname.

## Requirements

### System Identity
- Kernel version
- RHEL release version (`/etc/redhat-release`)
- Hostname, FQDN, architecture
- Uptime
- CPU and memory specs

### Platform
- VMware, AWS EC2, Azure VM, bare metal, or other
- Boot mode (UEFI / BIOS)
- Init system (systemd / sysvinit)

### Storage
- Disk/partition/volume layout, usage, and capacity (`lsblk`, `df`)
- LVM details (PVs, VGs, LVs)
- `/etc/fstab`
- Multipath config
- NFS/CIFS mounts

### Network
- Interfaces, IPs, routes, DNS
- NetworkManager in use?
- Bonding/teaming config
- Legacy ifcfg network-scripts

### Firewall
- iptables or firewalld in use?
- nftables rules (RHEL 8+)
- Active rules dump

### Security & Access
- SELinux status and config
- Sudoers (all, including `/etc/sudoers.d/*`)
- SSHD config (including drop-ins)
- PAM config (system-auth, password-auth, sshd, su)
- Crypto policies (RHEL 8+)

### Identity / Domain Join
- SSSD, realm, and krb5 configs
- Kerberos keytab presence
- nsswitch.conf

### Services
- Enabled/running services (systemd or chkconfig)
- Tuned profile

### Packages & Repos
- Satellite server attached to
- Subscription status
- Enabled repos
- Non-satellite repos (baseurl, mirrorlist, metalink)
- yum/dnf versionlocks
- Date of last kernel update
- Total package count
- Non-Red Hat packages (vendor breakdown)

### Kernel
- Loaded kernel modules
- Third-party / custom kernel modules
- Deprecated modules

### Backup & Monitoring
- Backup/restore agents (NetBackup, Commvault, TSM, Veeam, Rubrik, Cohesity, Bacula, Amanda)
- Monitoring agents (Zabbix, Nagios, Splunk, Datadog, CrowdStrike, Qualys, Tanium)

### Filesystem Exploration
- Subdirectory listing of `/opt` and `/data`
- Third-party software in common paths (`/opt`, `/usr/local/bin`, `/usr/local/sbin`)

### RHEL 9/10 Migration Readiness
- Python versions installed (RHEL 9 drops Python 2)
- 32-bit packages (many removed in RHEL 9)
- Deprecated packages (ntp, sendmail, xinetd, iptables-services, net-tools, etc.)
- chronyd vs ntpd status
- Legacy network-scripts vs NetworkManager
- OpenSSL version
- Common server apps (httpd, nginx, MySQL, MariaDB, PostgreSQL, Tomcat, Java, Docker, Podman)
- Cron jobs (root crontab, `/etc/crontab`, `/etc/cron.d/`)
- fstab concerns (NFS/CIFS, ext2/3, deprecated mount options)

## Usage

```bash
# Edit inventory with your hosts
vim inventory/hosts.yml

# Run against all hosts
ansible-playbook gather_facts.yml

# Run against a specific group or host
ansible-playbook gather_facts.yml --limit rhel8
ansible-playbook gather_facts.yml --limit server1.example.com

# Run specific sections only
ansible-playbook gather_facts.yml --tags selinux,network,migration
```

## Output

Report is written to `./output/discovery_report.yml` — a single YAML file with all hosts keyed by hostname.

## Prerequisites

- Ansible 2.9+ (2.11 for RHEL 6 targets with Python 2.6)
- SSH access to target hosts
- `become` (sudo) privileges on targets
- Python 2.6+ on RHEL 6, Python 2.7+ on RHEL 7, platform-python on RHEL 8
