# cc-disco — Server Discovery as Ansible Facts

Read-only Ansible discovery for Linux and Windows servers. Everything discovered is published as **cacheable Ansible facts**: it lands in `ansible_facts`, the fact cache, and AAP fact storage. A per-host JSON copy is also written to `output/facts/<host>.json`.

Two layers:

- **Inventory** (every host: RHEL 6–10, Ubuntu, Windows Server). Installed packages, component versions, services, running processes, listening ports, pending security updates and running containers, for vulnerability response.
- **Migration** (RHEL-family 6/7/8 only). Configuration needed to plan an upgrade to RHEL 9/10: kernel modules, network config, firewall rules, storage config, sudo/sshd/PAM, identity, Satellite, agents, and readiness checks.

Nothing is modified on target hosts. Data that `setup`, `package_facts` or `service_facts` already provide is never collected a second time; the playbook only adds what they lack.

## Usage

```bash
ansible-galaxy collection install -r requirements.yml   # only needed for Windows hosts

ansible-playbook gather_facts.yml                        # all hosts
ansible-playbook gather_facts.yml --limit rhel8          # a group
ansible-playbook gather_facts.yml --tags packages,processes,ports
ansible-playbook gather_facts.yml -e disco_mode=lightweight
ansible-playbook gather_facts.yml -e disco_profile=inventory   # skip the migration layer on RHEL 6/7/8
```

Windows hosts must be in the `windows` inventory group with their connection settings (see `inventory/hosts.yml`).

## Output

- **Facts.** Each host's `ansible_facts` holds the setup facts plus everything listed below. They are stored in the jsonfile fact cache (`./tmp/ansible_fact_cache`) or, under AAP, in the controller's fact storage when "Enable Fact Storage" is on.
- **`output/facts/<inventory_hostname>.json`.** A copy of each host's `ansible_facts`, written by the final play.

Each run starts by clearing cached facts, so the output is a fresh snapshot: a `--tags` run contains only the selected sections, plus setup facts and `disco_controls`.

**Null convention.** `null` means *not collected*: the probe was skipped, the source was missing, or the command failed. An empty list means the probe ran and found nothing. Placeholder strings such as `"not found"` are never used.

> **Sensitive data.** The migration layer collects sudoers, sshd, PAM, SSSD and Kerberos configuration. `ldap_default_authtok` is redacted from `sssd.conf`, but treat the fact cache, AAP host facts and `output/facts/` with the same care as a credentials file.

## Fact catalogue

### Every host (inventory layer)

| Fact | Linux | Windows |
|---|---|---|
| setup facts | `ansible_facts.*` (OS, kernel, CPU, memory, interfaces, mounts, LVM, SELinux, DMI, virtualisation, …) | `ansible_facts.*` (OS, domain, interfaces, BIOS, reboot pending, PowerShell version, …) |
| `packages` | `package_facts`: `{name: [{version, release, arch, …}]}` | Uninstall registry keys in the same shape: `{name: [{version, publisher, install_date, arch, source}]}` |
| `services` | `service_facts`: `{name: {state, status, source}}` | `win_service_info` in the same shape, plus `display_name`, `start_mode`, `path`, `username` |
| `tcp_listen` / `udp_listen` | from `ss -tulpn` (or netstat): `[{protocol, address, port, name, pid, user}]` | `win_listen_ports_facts` (same shape) |
| `disco_processes` | `[{pid, ppid, user, name, command}]` (kernel threads excluded) | same keys plus `path` and `file_version` |
| `disco_packages` | `third_party` (rpm vendor / apt origin isn't the OS vendor), `repos`, `locks` (versionlock / apt holds), `security_updates`, `snaps`, `last_kernel_update` | `hotfixes` (KBs), `features` (installed Server roles/features) |
| `disco_components` | `openssl`, `java` (active `java -version`), `python` (python, python2, python3, platform-python) | `os` (product, edition, DisplayVersion, CurrentBuild, **UBR**, `build`), `dotnet_framework_release` |
| `disco_containers` | running podman/docker containers `[{runtime, id, name, image, image_id, status, ports}]` | running docker containers |
| `disco_controls` | profile, mode, knob values, omitted sections, run tags, collection time | same |

Notes:
- `security_updates` comes from cache-only `dnf/yum updateinfo` or `apt list --upgradable` (filtered to `-security` pockets), so it reflects the host's last metadata refresh. It is not collected on Windows: a Windows Update search can take many minutes.
- Containers are those visible to root. Rootless containers of other users aren't listed.
- Ubuntu needs `python3-apt` for `package_facts`. It is present on server images; without it `packages` is null.

### RHEL-family 6/7/8 (migration layer)

| Fact | Contents | Already in setup facts, so not collected |
|---|---|---|
| `disco_platform` | `boot_mode`, AWS/Azure IMDS results, derived `detected` platform | DMI vendor/product, virtualisation type |
| `disco_kernel` | loaded modules, third-party modules, deprecated modules, GRUB defaults, tuned profile | running kernel, cmdline |
| `disco_network` | routes, nmcli profiles, teaming state, ifcfg files | interfaces, bonding, DNS / resolv.conf |
| `disco_firewall` | firewalld zones, iptables rules, nftables ruleset | which firewall service runs (`services`) |
| `disco_storage` | fstab, multipath topology | mounts and usage, block devices, LVM |
| `disco_security` | sudoers (+ drop-ins), sshd_config (+ drop-ins), PAM, crypto policy | — |
| `disco_identity` | sssd.conf (redacted), realm list, krb5.conf, keytab present, nsswitch.conf | — |
| `disco_satellite` | subscription identity/status, rhsm server, katello packages, non-Satellite repos | — |
| `disco_backup` | backup/monitoring agents detected by path (NetBackup, Commvault, TSM, Veeam, Rubrik, Cohesity, Bacula, Amanda, Zabbix, Nagios, Splunk, Datadog, CrowdStrike, Qualys, Tanium) | — |
| `disco_filesystem` | `/opt` and `/data` subdirectories, contents of `/usr/local/{bin,sbin}`, `/app`, `/apps`, `/software` | — |
| `disco_readiness` | 32-bit packages, deprecated packages, Java packages, fstab concerns, xinetd services, alternatives, crontabs, cron.d | SELinux status, init system, time-service and NetworkManager state |
| `disco_apps` | common server apps (httpd, nginx, MySQL/MariaDB, PostgreSQL, Tomcat, Java, Docker, Podman) | — |

## Performance controls

- `disco_mode`: `full` (default) or `lightweight`. Lightweight sets all knobs below to false.
- `disco_collect_deep_security`: sudoers.d, sshd_config.d and PAM collection.
- `disco_collect_deep_kernel`: third-party and deprecated kernel module analysis.
- `disco_collect_deep_filesystem`: filesystem exploration.
- `disco_collect_command_heavy_probes`: repos, version locks, pending security updates, non-Satellite repos, agents, and most readiness probes.

Skipped probes publish `null`, and `disco_controls.omitted` lists the knobs that were off.

`ansible.cfg` defaults to `forks = 25`. Override per run with `ANSIBLE_FORKS=50 ansible-playbook gather_facts.yml`. The discovery plays use `strategy: free`, so each host moves through its tasks at its own pace and one slow host doesn't stall the batch. Task output from different hosts is interleaved as a result.

## Tags

Each task file has one primary tag matching its name: `packages`, `services`, `processes`, `ports`, `components`, `containers`, and the migration sections (`platform`, `kernel`, `network`, `firewall`, `storage`, `security`, `identity`, `satellite`, `backup`, `filesystem`, `readiness`, `apps`). `deep_kernel`, `deep_security` and `deep_filesystem` select only the expensive probes plus their section's publish task.

Some sections read data collected by another. The producing tasks already carry the consumer's tag, so `--tags readiness` pulls in what it needs:

| Producer | Data | Consumers |
|---|---|---|
| `packages` (package_facts) | `ansible_facts.packages` | `readiness`, `apps`, `satellite` |
| `services` (service_facts) | `ansible_facts.services` | `firewall` |
| `processes` (ps) | process owners | `ports` |
| `storage` (fstab) | fstab content | `readiness` |

## Controller requirements

ansible-core dropped support for older target Pythons over time, so a mixed estate needs more than one controller version:

| Targets | Target Python | ansible-core |
|---|---|---|
| RHEL 6 | 2.6 | **2.11** (last release supporting Python 2.6 targets) |
| RHEL 7, RHEL 8 (platform-python) | 2.7, 3.6 | 2.12 – **2.16** |
| RHEL 9, RHEL 10, Ubuntu 20.04–24.04 | 3.8 – 3.12 | 2.16 or later |
| Windows Server | PowerShell 5.1 | 2.16 or later, plus `ansible.windows` ≥ 2.7.0 |
| Python 3.13+ targets (e.g. Ubuntu 26.04) | 3.13+ | 2.18 or later (which can't manage RHEL 7/8 without a newer Python) |

**ansible-core 2.16 covers everything except RHEL 6.** Run RHEL 6 hosts from a 2.11 controller (the integration tests do both). Linux tasks use `ansible.builtin` only. The Windows task files are included dynamically, so a 2.11 controller without `ansible.windows` still parses the playbook.

Targets also need SSH (WinRM, PSRP or SSH for Windows) and sudo (`become`) on Linux.

**SSH to RHEL 6 from a modern controller.** RHEL 6 runs OpenSSH 5.3. With **ECDSA** host keys and an ECDSA login key (RHEL 6.5+), a current controller connects with its default crypto policy and no extra options; the integration tests run this way.
- **RSA** keys fall back to `ssh-rsa` (SHA-1), which OpenSSH 8.8+ refuses. They need `-o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa` and, on EL9+, the `LEGACY` crypto policy.
- **ed25519** keys don't work against RHEL 6.

## Tests

```bash
ansible-lint                        # production profile
pytest tests/ --ignore=tests/integration   # conventions + publish-fact rendering
make -C tests/integration test-integration # containers: EL6 (core 2.11), EL7/EL9/EL10/Ubuntu (core 2.16)
COMPOSE="podman compose" CONTAINER_CLI=podman pytest tests/integration -v
```

### Windows verification (manual)

Windows can't run in the container suite. Against a Windows Server 2019/2022 VM in the `windows` group:

1. `ansible-playbook gather_facts.yml --limit windows`. The recap shows `changed=0` for the Windows host; only the localhost export task changes.
2. In `output/facts/<host>.json`, check:
   - `packages` lists installed programs;
   - `services` has `W3SVC`/`WinRM` entries in service_facts shape;
   - `disco_packages.hotfixes` lists KBs;
   - `disco_components.os.build` looks like `20348.2762`;
   - `tcp_listen` includes the WinRM port (5985/5986);
   - `disco_processes` has `path` and `file_version`.
