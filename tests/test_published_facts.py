"""Render each publishing set_fact against registered-result fixtures.

Covers the parsers (ps, ss/netstat, rpm vendor, updateinfo, apt, snap, podman/docker,
Windows registry/services) and the null convention: null means "not collected",
lists are always lists, and no English placeholders or empty strings stand in for null.
"""
import pytest

from conftest import (
    TASKS_DIR, assert_no_placeholders, cmd, controls_vars, evaluate, missing_cmd,
    probes, publish, skipped, stat, uri,
)


def _ctx(facts, extra=None, **registered):
    """Context for a host: rendered vars/controls.yml + setup facts + registered results."""
    return {**controls_vars(facts, extra), "ansible_facts": facts, **registered}


# ---------------------------------------------------------------------------
# disco_collected: the one "was this probe collected?" check
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("result,expected", [
    (cmd("out"), True),
    (cmd(""), True),
    (cmd("", rc=1), False),
    (missing_cmd(), False),
    (skipped(), False),
    (None, False),
    ({"failed": False, "msg": "stat failed"}, False),
    ({"failed": False, "msg": "/data was skipped as it does not exist"}, False),
    (stat(False), True),
    (uri(-1), True),
    ({"output": []}, True),
    ({"services": []}, True),
])
def test_disco_collected(result, expected):
    assert evaluate("r is disco_collected", {"r": result}) is expected


def test_disco_collected_undefined_register():
    """A register that never ran (outside the selected --tags) is not collected."""
    assert evaluate("r is disco_collected", {}) is False
    assert evaluate("r is not disco_collected", {}) is True


# ---------------------------------------------------------------------------
# Profile selection and controls
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("distribution,major,expected", [
    ("RedHat", "6", "migration"),
    ("CentOS", "7", "migration"),
    ("RedHat", "8", "migration"),
    ("Rocky", "8", "migration"),
    ("RedHat", "9", "inventory"),
    ("RedHat", "10", "inventory"),
    ("Amazon", "2", "inventory"),
    ("Ubuntu", "24", "inventory"),
    ("Microsoft Windows Server 2022 Standard", "10", "inventory"),
])
def test_migration_profile_applies_to_rhel_6_to_8_only(distribution, major, expected):
    v = controls_vars({"distribution": distribution, "distribution_major_version": major}, {"disco_profile": "migration"})
    assert v["discovery_profile"].strip() == expected


@pytest.mark.parametrize("distribution,major", [("RedHat", "6"), ("CentOS", "7"), ("RedHat", "8"), ("Ubuntu", "24")])
def test_inventory_is_the_default_profile(distribution, major):
    v = controls_vars({"distribution": distribution, "distribution_major_version": major})
    assert v["discovery_profile"].strip() == "inventory"


@pytest.mark.parametrize("pkg_mgr,family,yum", [
    ("dnf", "rpm", "dnf -C -q --disableplugin=subscription-manager,product-id"),
    ("yum", "rpm", "yum -C -q --disableplugin=subscription-manager,product-id"),
    ("dnf5", "rpm", "dnf -C -q"),
    ("apt", "apt", None),
    ("zypper", "other", None),
])
def test_package_manager_helpers(pkg_mgr, family, yum):
    v = controls_vars({"distribution": "X", "pkg_mgr": pkg_mgr})
    assert v["disco_pkg_family"].strip() == family
    if yum:
        assert v["disco_yum"].strip() == yum


def test_controls_lightweight_mode(rhel8_facts):
    ctx = _ctx(rhel8_facts, {"disco_mode": "lightweight", "disco_profile": "migration"}, ansible_run_tags=["all"])
    controls = publish("tasks/controls.yml", ctx)["disco_controls"]
    assert controls["profile"] == "migration"
    assert controls["mode"] == "lightweight"
    assert controls["collect_command_heavy_probes"] is False
    assert controls["omitted"] == ["deep_security", "deep_kernel", "deep_filesystem", "command_heavy_probes"]
    assert controls["collected_at"] == "2026-10-28T12:00:00Z"


# ---------------------------------------------------------------------------
# Linux inventory layer
# ---------------------------------------------------------------------------

RPM_VENDORS = "\n".join([
    "bash|4.4.20-4.el8.x86_64|Red Hat, Inc.",
    "gpg-pubkey|fd431d51-4ae0493b.(none)|(none)",
    "nginx|1.20.1-1.el8.x86_64|Fedora Project",
    "falcon-sensor|7.10.0-16303.el8.x86_64|CrowdStrike, Inc.",
    "custom-tool|1.0-1.noarch|(none)",
])
UPDATEINFO = "\n".join([
    "RHSA-2024:1234 Important/Sec. openssl-libs-1:1.1.1k-12.el8_9.x86_64",
    "RHSA-2024:2001 Moderate/Sec.  curl-7.61.1-34.el8.x86_64",
])


def test_packages_rpm(rhel8_facts):
    facts = publish("tasks/linux/packages.yml", _ctx(
        rhel8_facts,
        disco_rpm_vendors=cmd(RPM_VENDORS),
        disco_last_kernel_update=cmd("kernel-4.18.0-513.el8.x86_64  Mon 01 Jan 2024 10:00:00 AM UTC"),
        disco_repos_enabled=cmd("repo id                    repo name\nrhel-8-for-x86_64-baseos-rpms   BaseOS\n!epel  EPEL 8"),
        disco_versionlocks=cmd("0:bash-4.4.20-4.el8.*"),
        disco_security_updates_rpm=cmd(UPDATEINFO),
        disco_apt_sources=skipped(), disco_apt_holds=skipped(), disco_security_updates_apt=skipped(),
        disco_snaps=missing_cmd(),
    ))["disco_packages"]
    assert facts["third_party"] == [
        {"name": "nginx", "version": "1.20.1-1.el8.x86_64", "vendor": "Fedora Project"},
        {"name": "falcon-sensor", "version": "7.10.0-16303.el8.x86_64", "vendor": "CrowdStrike, Inc."},
        {"name": "custom-tool", "version": "1.0-1.noarch", "vendor": None},
    ]
    assert facts["repos"] == ["rhel-8-for-x86_64-baseos-rpms", "epel"]
    assert facts["locks"] == ["0:bash-4.4.20-4.el8.*"]
    assert facts["security_updates"][0] == {
        "advisory": "RHSA-2024:1234", "severity": "Important",
        "package": "openssl-libs-1:1.1.1k-12.el8_9.x86_64", "version": None, "source": None,
    }
    assert len(facts["security_updates"]) == 2
    assert facts["snaps"] is None
    assert facts["last_kernel_update"].startswith("kernel-4.18.0-513")


def test_packages_rpm_lightweight_probes_skipped(rhel8_facts):
    facts = publish("tasks/linux/packages.yml", _ctx(
        rhel8_facts,
        disco_rpm_vendors=cmd(RPM_VENDORS),
        disco_last_kernel_update=cmd(""),
        disco_repos_enabled=skipped(), disco_versionlocks=skipped(), disco_security_updates_rpm=skipped(),
        disco_apt_sources=skipped(), disco_apt_holds=skipped(), disco_security_updates_apt=skipped(),
        disco_snaps=missing_cmd(),
    ))["disco_packages"]
    assert facts["repos"] is None
    assert facts["locks"] is None
    assert facts["security_updates"] is None
    assert facts["last_kernel_update"] is None
    assert isinstance(facts["third_party"], list)


def test_packages_apt(ubuntu_facts):
    facts = publish("tasks/linux/packages.yml", _ctx(
        ubuntu_facts,
        disco_rpm_vendors=skipped(), disco_last_kernel_update=skipped(),
        disco_repos_enabled=skipped(), disco_versionlocks=skipped(), disco_security_updates_rpm=skipped(),
        disco_apt_sources=cmd("URIs: http://archive.ubuntu.com/ubuntu/\nSuites: noble noble-updates"),
        disco_apt_holds=cmd("docker-ce"),
        disco_security_updates_apt=cmd(
            "Listing...\n"
            "openssl/noble-updates,noble-security 3.0.13-0ubuntu3.5 amd64 [upgradable from: 3.0.13-0ubuntu3.4]\n"
            "vim/noble-updates 2:9.1.0016-1ubuntu7.4 amd64 [upgradable from: 2:9.1.0016-1ubuntu7.3]"
        ),
        disco_snaps=cmd(
            "Name    Version        Rev    Tracking       Publisher   Notes\n"
            "core22  20240904       1663   latest/stable  canonical✓  base\n"
            "lxd     5.21.2-2f4ba6b 30131  5.21/stable    canonical✓  -"
        ),
    ))["disco_packages"]
    assert facts["third_party"] == [
        {"name": "docker-ce", "version": "5:27.3.1-1~ubuntu.24.04~noble", "vendor": "Docker"},
        {"name": "localtool", "version": "1.0", "vendor": None},
    ]
    assert facts["repos"] == ["URIs: http://archive.ubuntu.com/ubuntu/", "Suites: noble noble-updates"]
    assert facts["locks"] == ["docker-ce"]
    assert facts["security_updates"] == [{
        "advisory": None, "severity": None, "package": "openssl",
        "version": "3.0.13-0ubuntu3.5", "source": "noble-updates,noble-security",
    }]
    assert [s["name"] for s in facts["snaps"]] == ["core22", "lxd"]
    assert facts["snaps"][1]["revision"] == "30131"
    assert facts["last_kernel_update"] is None


PS_OUTPUT = "\n".join([
    "      1       0 root                             /usr/lib/systemd/systemd --switched-root --system",
    "      2       0 root                             [kthreadd]",
    "     15       2 root                             [ksoftirqd/0]",
    "    812       1 root                             /usr/sbin/sshd -D",
    "    813       1 root                             sshd: /usr/sbin/sshd -D [listener] 0 of 10-100 startups",
    "   1044       1 nginx                            nginx: worker process",
    "   2201       1 postgres-backup                  /usr/pgsql-15/bin/postgres -D /var/lib/pgsql/15/data",
])


def test_processes():
    facts = publish("tasks/linux/processes.yml", {"disco_ps": cmd(PS_OUTPUT)})
    procs = facts["disco_processes"]
    assert [p["pid"] for p in procs] == [1, 812, 813, 1044, 2201]
    assert procs[1] == {"pid": 812, "ppid": 1, "user": "root", "name": "sshd", "command": "/usr/sbin/sshd -D"}
    # setproctitle names ("sshd: ...", "nginx: worker process") lose the colon.
    assert procs[2]["name"] == "sshd"
    assert procs[3]["name"] == "nginx"
    assert procs[4]["user"] == "postgres-backup"


def test_processes_unavailable_is_null():
    facts = publish("tasks/linux/processes.yml", {"disco_ps": cmd("", rc=1)})
    assert facts == {"disco_processes": None}


SS_MODERN = "\n".join([
    'ss|tcp|0.0.0.0:22|users:(("sshd",pid=812,fd=3))',
    'ss|tcp|[::]:22|users:(("sshd",pid=812,fd=4))',
    'ss|tcp|127.0.0.1:5432|users:(("postgres",pid=2201,fd=6),("postgres",pid=2202,fd=6))',
    'ss|udp|127.0.0.53%lo:53|users:(("systemd-resolve",pid=600,fd=13))',
    'ss|tcp|0.0.0.0:9100|',
])
SS_RHEL6 = "\n".join([
    'ss|tcp|*:22|users:(("sshd",1201,3))',
    'ss|tcp|:::22|users:(("sshd",1201,4))',
])
NETSTAT = "\n".join([
    "netstat|tcp|0.0.0.0:22|812/sshd",
    "netstat|tcp6|:::80|1044/nginx: master",
    "netstat|udp|0.0.0.0:68|-",
])


def test_ports_modern_ss():
    facts = publish("tasks/linux/ports.yml", {"disco_listen": cmd(SS_MODERN), "disco_ps": cmd(PS_OUTPUT)})
    tcp, udp = facts["tcp_listen"], facts["udp_listen"]
    assert tcp[0] == {"protocol": "tcp", "address": "0.0.0.0", "port": 22, "name": "sshd", "pid": 812, "user": "root"}
    assert tcp[1]["protocol"] == "tcp6" and tcp[1]["address"] == "::"
    assert tcp[2]["name"] == "postgres" and tcp[2]["pid"] == 2201 and tcp[2]["user"] == "postgres-backup"
    assert tcp[3] == {"protocol": "tcp", "address": "0.0.0.0", "port": 9100, "name": None, "pid": None, "user": None}
    assert udp == [{"protocol": "udp", "address": "127.0.0.53", "port": 53, "name": "systemd-resolve", "pid": 600, "user": None}]


def test_ports_rhel6_ss():
    tcp = publish("tasks/linux/ports.yml", {"disco_listen": cmd(SS_RHEL6), "disco_ps": cmd("")})["tcp_listen"]
    assert [(p["protocol"], p["address"], p["port"], p["name"], p["pid"]) for p in tcp] == [
        ("tcp", "*", 22, "sshd", 1201),
        ("tcp6", "::", 22, "sshd", 1201),
    ]


def test_ports_netstat():
    facts = publish("tasks/linux/ports.yml", {"disco_listen": cmd(NETSTAT), "disco_ps": cmd(PS_OUTPUT)})
    assert facts["tcp_listen"][0]["name"] == "sshd"
    assert facts["tcp_listen"][1] == {"protocol": "tcp6", "address": "::", "port": 80, "name": "nginx: master", "pid": 1044, "user": "nginx"}
    assert facts["udp_listen"][0]["pid"] is None


def test_ports_unavailable_is_null():
    facts = publish("tasks/linux/ports.yml", {"disco_listen": cmd("", rc=127), "disco_ps": cmd("")})
    assert facts == {"tcp_listen": None, "udp_listen": None}


def test_components():
    facts = publish("tasks/linux/components.yml", {
        "disco_openssl_version": cmd("OpenSSL 1.1.1k  FIPS 25 Mar 2021"),
        "disco_java_active": cmd("", stderr='openjdk version "1.8.0_362"\nOpenJDK Runtime Environment'),
        "disco_python_versions": cmd("python|\npython2|Python 2.7.5\npython3|Python 3.6.8\nplatform-python|Python 3.6.8"),
    })["disco_components"]
    assert facts["openssl"] == "OpenSSL 1.1.1k  FIPS 25 Mar 2021"
    assert facts["java"].startswith('openjdk version "1.8.0_362"')
    assert facts["python"] == {"python": None, "python2": "Python 2.7.5", "python3": "Python 3.6.8", "platform-python": "Python 3.6.8"}


def test_components_absent():
    facts = publish("tasks/linux/components.yml", {
        "disco_openssl_version": missing_cmd(),
        "disco_java_active": missing_cmd(),
        "disco_python_versions": cmd("python|\npython2|\npython3|Python 3.12.3\nplatform-python|"),
    })["disco_components"]
    assert facts["openssl"] is None
    assert facts["java"] is None
    assert facts["python"]["python3"] == "Python 3.12.3"


PODMAN_V4 = """[{"Id": "a208635d", "Names": ["web"], "Image": "docker.io/library/nginx:1.27", "ImageID": "e94d73",
  "State": "running", "Status": "Up 2 hours", "Ports": [{"host_port": 8080, "container_port": 80, "protocol": "tcp"}]}]"""
PODMAN_V1 = """[{"ID": "b1c2", "Names": "db", "Image": "registry.access.redhat.com/rhel8/postgresql-13", "Status": "Up 5 days", "Ports": ""}]"""
DOCKER_LINES = "\n".join([
    '{"ID":"a208635d","Names":"web","Image":"nginx:1.27","Status":"Up 2 hours","Ports":"0.0.0.0:8080->80/tcp"}',
    '{"ID":"ffee01","Names":"cache","Image":"redis:7","Status":"Up 1 day","Ports":""}',
])


def test_containers_dedupes_podman_docker_shim():
    facts = publish("tasks/linux/containers.yml", {"disco_podman_ps": cmd(PODMAN_V4), "disco_docker_ps": cmd(DOCKER_LINES)})
    containers = facts["disco_containers"]
    assert [(c["runtime"], c["id"]) for c in containers] == [("podman", "a208635d"), ("docker", "ffee01")]
    assert containers[0]["name"] == "web" and containers[0]["image_id"] == "e94d73"
    assert containers[1]["ports"] is None


def test_containers_podman_v1():
    facts = publish("tasks/linux/containers.yml", {"disco_podman_ps": cmd(PODMAN_V1), "disco_docker_ps": missing_cmd()})
    assert facts["disco_containers"] == [{
        "runtime": "podman", "id": "b1c2", "name": "db", "image": "registry.access.redhat.com/rhel8/postgresql-13",
        "image_id": None, "status": "Up 5 days", "ports": "",
    }]


def test_containers_no_runtime_is_null():
    facts = publish("tasks/linux/containers.yml", {"disco_podman_ps": missing_cmd(), "disco_docker_ps": missing_cmd()})
    assert facts == {"disco_containers": None}


def test_containers_runtime_with_none_running():
    facts = publish("tasks/linux/containers.yml", {"disco_podman_ps": cmd("[]"), "disco_docker_ps": missing_cmd()})
    assert facts == {"disco_containers": []}


# ---------------------------------------------------------------------------
# Migration layer
# ---------------------------------------------------------------------------

# Batched probe output per migration section: name -> output, or (rc, output).
FULL_PROBES = {
    "kernel": {
        "lsmod": "Module                  Size  Used by\nvmw_balloon            20480  0\nfloppy  1  0",
        "third_party_modules": "vmw_balloon|/lib/modules/extra/vmw_balloon.ko|VMware, Inc.",
        "grub": "GRUB_TIMEOUT=5\nGRUB_DEFAULT=saved",
        "tuned": "Current active profile: virtual-guest",
    },
    "network": {
        "routes": "default via 10.0.1.1 dev eth0\n10.0.1.0/24 dev eth0 proto kernel",
        "nmcli": "eth0:uuid1:802-3-ethernet:eth0",
        "teaming": "",
        "ifcfg": "/etc/sysconfig/network-scripts/ifcfg-eth0",
    },
    "firewall": {
        "firewalld": "public (active)\n  services: ssh",
        "iptables": "Chain INPUT (policy ACCEPT)",
        "nftables": "",
    },
    "storage": {
        "fstab": "/dev/sda1 / xfs defaults 0 0\n# nfs comment\nnas:/export /mnt/nas nfs defaults,_netdev 0 0",
        "multipath": (1, ""),
    },
    "security": {
        "sudoers": "root ALL=(ALL) ALL",
        "sshd_config": "PermitRootLogin no",
        "sudoers_d": "",
        "sudoers_d:/etc/sudoers.d/admins": "%admins ALL=(ALL) NOPASSWD: ALL",
        "sshd_d": "",
        "pam": "",
        "pam:/etc/pam.d/system-auth": "auth required pam_env.so",
        "pam:/etc/pam.d/su": (1, ""),
        "crypto_policy": "DEFAULT",
    },
    "identity": {
        "sssd": "[domain/example.com]\nldap_default_authtok = s3cret\nid_provider = ldap",
        "realm": "example.com\n  type: kerberos",
        "krb5": "[libdefaults]\ndefault_realm = EXAMPLE.COM",
        "keytab": "true",
        "nsswitch": "passwd: files sss",
    },
    "satellite": {
        "identity": "system identity: 12345",
        "status": "Overall Status: Current",
        "rhsm": "hostname = satellite.example.com\nbaseurl = https://satellite.example.com/pulp/repos",
        "non_satellite_repos": "",
    },
    "filesystem": {
        "opt": "/opt/splunkforwarder\n/opt/CrowdStrike",
        "data": "",
        "third_party_paths": "=== /usr/local/bin ===\ncustom-tool",
    },
    "readiness": {
        "fstab": "/dev/sda1 / xfs defaults 0 0\n# nfs comment\nnas:/export /mnt/nas nfs defaults,_netdev 0 0",
        "xinetd": "",
        "alternatives": "java\tauto\t/usr/lib/jvm/jre/bin/java",
        "root_crontab": "0 2 * * * /usr/local/bin/backup.sh",
        "system_crontab": "SHELL=/bin/bash",
        "cron_d": "/etc/cron.d/0hourly",
    },
}

# Every probe ran and found nothing (or the source was missing). Absent names didn't run.
EMPTY_PROBES = {
    "kernel": {"lsmod": "", "third_party_modules": "", "grub": (1, ""), "tuned": (127, "")},
    "network": {"routes": "", "nmcli": (127, ""), "teaming": "", "ifcfg": ""},
    "firewall": {"iptables": (127, "")},
    "storage": {"fstab": (1, ""), "multipath": (127, "")},
    "security": {"sudoers": "", "sshd_config": "", "sudoers_d": "", "sshd_d": "", "pam": ""},
    "identity": {"sssd": (1, ""), "realm": (127, ""), "krb5": "", "keytab": "false", "nsswitch": ""},
    "satellite": {
        "identity": (1, "This system is not yet registered."), "status": (127, ""),
        "rhsm": (2, ""), "non_satellite_repos": "",
    },
    "filesystem": {"opt": "", "data": "", "third_party_paths": ""},
    "readiness": {
        "fstab": (1, ""), "xinetd": "", "alternatives": "", "root_crontab": (1, ""),
        "system_crontab": "", "cron_d": "",
    },
}


def _registers(probe_sets, **registered):
    """Registers for a migration run: one batched probe register per section, plus overrides."""
    regs = {f"disco_{section}_probes": probes(entries) for section, entries in probe_sets.items()}
    return {**regs, **registered}


def _without(probe_sets, **names):
    """probe_sets with the given names dropped per section (probes that didn't run)."""
    return {
        section: {k: v for k, v in entries.items() if k.split(":")[0] not in names.get(section, ())}
        for section, entries in probe_sets.items()
    }


FULL_MIGRATION = _registers(
    FULL_PROBES,
    disco_efi_dir=stat(True), disco_ec2_check=skipped(), disco_azure_check=skipped(),
    disco_backup_monitoring=cmd("crowdstrike\nsplunk"),
)
EMPTY_MIGRATION = _registers(
    EMPTY_PROBES,
    disco_efi_dir=stat(False), disco_ec2_check=uri(-1), disco_azure_check=uri(-1),
    disco_backup_monitoring=cmd(""),
)

MIGRATION_FILES = sorted(p.stem for p in (TASKS_DIR / "migration").glob("*.yml"))


def _migration(facts, registered, extra=None):
    ctx = _ctx(facts, extra, **registered)
    published = {}
    for name in MIGRATION_FILES:
        published.update(publish(f"tasks/migration/{name}.yml", ctx))
    return published


def test_migration_full(rhel8_facts):
    f = _migration(rhel8_facts, FULL_MIGRATION)
    assert set(f) == {f"disco_{n}" for n in MIGRATION_FILES}
    assert f["disco_platform"] == {"boot_mode": "UEFI", "aws_imds": None, "azure_imds": None, "detected": "vmware"}
    assert f["disco_kernel"]["loaded_modules"] == ["vmw_balloon", "floppy"]
    assert f["disco_kernel"]["third_party_modules"][0]["author"] == "VMware, Inc."
    assert f["disco_kernel"]["deprecated_modules"] == ["floppy"]
    assert f["disco_kernel"]["tuned_profile"] == "virtual-guest"
    assert f["disco_network"]["ifcfg_files"] == ["/etc/sysconfig/network-scripts/ifcfg-eth0"]
    assert f["disco_network"]["teaming"] is None
    assert f["disco_firewall"]["nftables_rules"] is None
    assert f["disco_storage"]["multipath"] is None
    assert f["disco_security"]["sudoers_drop_ins"] == [{"file": "/etc/sudoers.d/admins", "content": "%admins ALL=(ALL) NOPASSWD: ALL"}]
    assert f["disco_security"]["pam"] == [{"file": "/etc/pam.d/system-auth", "content": "auth required pam_env.so"}]
    assert f["disco_identity"]["krb5_keytab_exists"] is True
    assert f["disco_satellite"]["katello_packages"] == ["katello-host-tools"]
    assert f["disco_satellite"]["rhsm_server"][0] == "hostname = satellite.example.com"
    assert f["disco_satellite"]["non_satellite_repos"] is None
    assert f["disco_backup"]["agents"] == ["crowdstrike", "splunk"]
    assert f["disco_filesystem"]["opt"] == ["/opt/CrowdStrike", "/opt/splunkforwarder"]
    r = f["disco_readiness"]
    assert r["packages_32bit"] == ["glibc-2.28-225.el8.i686"]
    assert r["deprecated_packages"] == ["ntp"]
    assert r["java_packages"] == ["java-1.8.0-openjdk-1.8.0.362-4.el8.x86_64"]
    assert r["fstab_concerns"] == ["nas:/export /mnt/nas nfs defaults,_netdev 0 0"]
    assert r["cron_d_entries"] == ["0hourly"]
    assert f["disco_apps"]["common"] == ["nginx", "java-1.8.0-openjdk"]
    assert_no_placeholders(f)


def test_sssd_bind_password_is_redacted(rhel8_facts):
    sssd = _migration(rhel8_facts, FULL_MIGRATION)["disco_identity"]["sssd_conf"]
    assert "s3cret" not in sssd
    assert "ldap_default_authtok = <redacted>" in sssd
    assert "id_provider = ldap" in sssd


def test_migration_empty_uses_null_and_empty_lists(rhel8_facts):
    facts = dict(rhel8_facts, packages={}, system_vendor="Dell Inc.", virtualization_role="host")
    f = _migration(facts, EMPTY_MIGRATION)
    assert f["disco_platform"] == {"boot_mode": "BIOS", "aws_imds": False, "azure_imds": False, "detected": "bare_metal"}
    nulls = [
        ("disco_kernel", "grub_defaults"), ("disco_kernel", "tuned_profile"),
        ("disco_network", "nmcli_connections"), ("disco_firewall", "firewalld_zones"),
        ("disco_firewall", "iptables_rules"), ("disco_storage", "fstab"), ("disco_storage", "multipath"),
        ("disco_security", "sudoers_main"), ("disco_security", "crypto_policy"),
        ("disco_identity", "sssd_conf"), ("disco_identity", "realm_list"),
        ("disco_satellite", "subscription_identity"), ("disco_satellite", "rhsm_server"),
        ("disco_satellite", "katello_packages"), ("disco_readiness", "packages_32bit"),
        ("disco_readiness", "fstab_concerns"), ("disco_readiness", "root_crontab"),
        ("disco_apps", "common"),
    ]
    for section, field in nulls:
        assert f[section][field] is None, f"{section}.{field} = {f[section][field]!r}"
    empty_lists = [
        ("disco_kernel", "loaded_modules"), ("disco_kernel", "third_party_modules"),
        ("disco_network", "routes"), ("disco_network", "ifcfg_files"),
        ("disco_security", "sudoers_drop_ins"), ("disco_security", "pam"),
        ("disco_backup", "agents"), ("disco_filesystem", "opt"), ("disco_readiness", "cron_d_entries"),
    ]
    for section, field in empty_lists:
        assert f[section][field] == [], f"{section}.{field} = {f[section][field]!r}"
    assert_no_placeholders(f)


def test_migration_lightweight_marks_skipped_probes_null(rhel8_facts):
    lightweight = _without(
        FULL_PROBES,
        kernel=["third_party_modules"], satellite=["non_satellite_repos"],
        security=["sudoers_d", "sshd_d", "pam"],
        readiness=["xinetd", "alternatives", "root_crontab", "system_crontab", "cron_d"],
    )
    del lightweight["filesystem"]
    registered = _registers(
        lightweight,
        disco_efi_dir=stat(True), disco_ec2_check=skipped(), disco_azure_check=skipped(),
        disco_backup_monitoring=skipped(), disco_filesystem_probes=skipped(),
    )
    f = _migration(rhel8_facts, registered, {"disco_mode": "lightweight"})
    assert f["disco_kernel"]["third_party_modules"] is None
    assert f["disco_kernel"]["deprecated_modules"] is None
    assert f["disco_security"]["sudoers_drop_ins"] is None
    assert f["disco_security"]["pam"] is None
    assert f["disco_backup"]["agents"] is None
    assert f["disco_filesystem"] == {"opt": None, "data": None, "third_party_paths": None}
    assert f["disco_readiness"]["xinetd_services"] is None
    assert f["disco_readiness"]["cron_d_entries"] is None
    # Package-derived readiness data is cheap and still collected.
    assert f["disco_readiness"]["deprecated_packages"] == ["ntp"]


@pytest.mark.parametrize("status,expected", [(200, "aws_ec2"), (401, "aws_ec2"), (-1, "kvm")])
def test_platform_aws_detection(status, expected):
    facts = {"system_vendor": "Amazon EC2", "virtualization_role": "guest", "virtualization_type": "kvm"}
    f = publish("tasks/migration/platform.yml", _ctx(
        facts, disco_efi_dir=stat(False), disco_ec2_check=uri(status), disco_azure_check=uri(-1),
    ))["disco_platform"]
    assert f["detected"] == expected


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def _ps(output):
    return {"output": output, "error": [], "changed": False}


def test_windows_packages():
    facts = publish("tasks/windows/packages.yml", {
        "disco_win_programs": _ps([
            {"name": "Google Chrome", "version": "130.0.6723.92", "publisher": "Google LLC", "install_date": "20241101", "arch": "x64"},
            {"name": "Microsoft Visual C++ 2015-2022 Redistributable", "version": "14.40.33810", "publisher": "Microsoft", "install_date": "", "arch": "x64"},
            {"name": "Microsoft Visual C++ 2015-2022 Redistributable", "version": "14.40.33810", "publisher": "Microsoft", "install_date": "", "arch": "x86"},
        ]),
        "disco_win_hotfixes": _ps([
            {"id": "KB5044281", "description": "Security Update", "installed_on": "2024-10-09"},
            {"id": "KB5043050", "description": "Update", "installed_on": None},
        ]),
        "disco_win_features": {"exists": True, "features": [
            {"name": "Web-Server", "installed": True}, {"name": "Hyper-V", "installed": False}, {"name": "FS-FileServer", "installed": True},
        ]},
    })
    pkgs = facts["packages"]
    assert pkgs["Google Chrome"] == [{
        "name": "Google Chrome", "version": "130.0.6723.92", "publisher": "Google LLC",
        "install_date": "20241101", "arch": "x64", "source": "registry",
    }]
    vcredist = pkgs["Microsoft Visual C++ 2015-2022 Redistributable"]
    assert [p["arch"] for p in vcredist] == ["x64", "x86"]
    assert vcredist[0]["install_date"] is None
    assert [h["id"] for h in facts["disco_packages"]["hotfixes"]] == ["KB5043050", "KB5044281"]
    assert facts["disco_packages"]["features"] == ["FS-FileServer", "Web-Server"]


def test_windows_packages_unavailable():
    facts = publish("tasks/windows/packages.yml", {
        "disco_win_programs": {"failed": False, "msg": "powershell error"},
        "disco_win_hotfixes": {"failed": False, "msg": "powershell error"},
        "disco_win_features": {"failed": False, "msg": "ServerManager module not found"},
    })
    assert facts["packages"] is None
    assert facts["disco_packages"] == {"hotfixes": None, "features": None}


def test_windows_services_mirror_service_facts():
    facts = publish("tasks/windows/services.yml", {"disco_win_services": {"exists": True, "services": [
        {"name": "W3SVC", "display_name": "World Wide Web Publishing Service", "state": "running",
         "start_mode": "auto", "path": "C:\\Windows\\system32\\svchost.exe -k iissvcs", "username": "LocalSystem"},
        {"name": "wuauserv", "display_name": "Windows Update", "state": "stopped", "start_mode": "manual",
         "path": "C:\\Windows\\system32\\svchost.exe -k netsvcs", "username": "LocalSystem"},
        {"name": "Spooler", "display_name": "Print Spooler", "state": "stopped", "start_mode": "disabled",
         "path": "C:\\Windows\\System32\\spoolsv.exe", "username": "LocalSystem"},
    ]}})
    svc = facts["services"]
    assert svc["W3SVC"]["state"] == "running" and svc["W3SVC"]["status"] == "enabled"
    assert svc["wuauserv"]["status"] == "manual"
    assert svc["Spooler"]["status"] == "disabled"
    assert svc["Spooler"]["source"] == "windows"


def test_windows_services_unavailable():
    assert publish("tasks/windows/services.yml", {"disco_win_services": {"failed": False, "msg": "x"}}) == {"services": None}


def test_windows_processes_sorted_by_pid():
    procs = publish("tasks/windows/processes.yml", {"disco_win_processes": _ps([
        {"pid": 4120, "ppid": 600, "user": "NT AUTHORITY\\SYSTEM", "name": "w3wp.exe", "command": "w3wp.exe -ap DefaultAppPool",
         "path": "C:\\Windows\\System32\\inetsrv\\w3wp.exe", "file_version": "10.0.20348.1"},
        {"pid": 4, "ppid": 0, "user": None, "name": "System", "command": None, "path": None, "file_version": None},
    ])})["disco_processes"]
    assert [p["pid"] for p in procs] == [4, 4120]


def test_windows_components_build():
    facts = publish("tasks/windows/components.yml", {"disco_win_components": _ps([{
        "product_name": "Windows Server 2022 Standard", "edition_id": "ServerStandard", "installation_type": "Server",
        "display_version": "21H2", "release_id": "2009", "current_build": "20348", "ubr": 2762,
        "dotnet_framework_release": 528449,
    }])})["disco_components"]
    assert facts["os"]["build"] == "20348.2762"
    assert facts["os"]["ubr"] == 2762
    assert facts["dotnet_framework_release"] == 528449


def test_windows_components_unavailable():
    facts = publish("tasks/windows/components.yml", {"disco_win_components": {"failed": False, "msg": "x"}})
    assert facts["disco_components"] == {"os": None, "dotnet_framework_release": None}


def test_windows_containers():
    facts = publish("tasks/windows/containers.yml", {"disco_docker_ps": cmd(
        '{"ID":"c0ffee","Names":"iis","Image":"mcr.microsoft.com/windows/servercore/iis","Status":"Up 3 hours","Ports":""}'
    )})
    assert facts["disco_containers"] == [{
        "runtime": "docker", "id": "c0ffee", "name": "iis", "image": "mcr.microsoft.com/windows/servercore/iis",
        "image_id": None, "status": "Up 3 hours", "ports": None,
    }]
    assert publish("tasks/windows/containers.yml", {"disco_docker_ps": missing_cmd()}) == {"disco_containers": None}


def test_package_derived_facts_tolerate_null_packages(rhel8_facts):
    """package_facts can fail (published as packages: null); derived facts become null, not errors."""
    facts = dict(rhel8_facts, packages=None)
    f = _migration(facts, FULL_MIGRATION)
    assert f["disco_apps"]["common"] is None
    assert f["disco_satellite"]["katello_packages"] is None
    assert f["disco_readiness"]["deprecated_packages"] is None
    pk = publish("tasks/linux/packages.yml", _ctx(
        dict(facts, pkg_mgr="apt"),
        disco_rpm_vendors=skipped(), disco_last_kernel_update=skipped(), disco_repos_enabled=skipped(),
        disco_versionlocks=skipped(), disco_security_updates_rpm=skipped(), disco_apt_sources=cmd(""),
        disco_apt_holds=cmd(""), disco_security_updates_apt=cmd("Listing..."), disco_snaps=missing_cmd(),
    ))
    assert pk["disco_packages"]["third_party"] is None
    assert "packages" not in pk  # the null fallback only fires when the fact is undefined


def test_services_and_packages_fallbacks_publish_null():
    assert publish("tasks/linux/services.yml", {"ansible_facts": {}}) == {"services": None}
    assert publish("tasks/linux/services.yml", {"ansible_facts": {"services": {}}}) == {}


def test_failed_probes_publish_null_not_empty(rhel8_facts):
    """A probe that ran and failed is "not collected", never "collected and empty"."""
    sets = {**FULL_PROBES, "kernel": {**FULL_PROBES["kernel"], "third_party_modules": (1, "")}}
    registered = _registers(
        _without(sets, identity=["keytab"]),
        disco_efi_dir={"failed": False, "msg": "stat failed"}, disco_ec2_check=skipped(), disco_azure_check=skipped(),
        disco_backup_monitoring=cmd("", rc=127),
    )
    f = _migration(rhel8_facts, registered)
    assert f["disco_backup"]["agents"] is None
    assert f["disco_kernel"]["third_party_modules"] is None
    assert f["disco_identity"]["krb5_keytab_exists"] is None
    assert f["disco_platform"]["boot_mode"] is None


def test_sshd_drop_ins_null_where_not_checked(rhel8_facts):
    """RHEL 6/7 have no sshd_config.d, so it isn't listed and nothing was collected."""
    registered = dict(FULL_MIGRATION, disco_security_probes=probes(_without(FULL_PROBES, security=["sshd_d"])["security"]))
    assert _migration(rhel8_facts, registered)["disco_security"]["sshd_config_drop_ins"] is None


def test_batched_probe_output_is_never_templated(rhel8_facts):
    """File contents travel base64-encoded and stay literal, even with | or {{ }} in them."""
    registered = dict(FULL_MIGRATION, disco_storage_probes=probes({"fstab": "a|b {{ 7 * 7 }}", "multipath": ""}))
    assert _migration(rhel8_facts, registered)["disco_storage"]["fstab"] == "a|b {{ 7 * 7 }}"


def test_whole_probe_task_skipped_publishes_nulls(rhel8_facts):
    """A section whose probe task never ran (e.g. outside --tags) publishes null fields."""
    f = publish("tasks/migration/network.yml", _ctx(rhel8_facts, disco_network_probes=skipped()))
    assert f["disco_network"] == {"routes": None, "nmcli_connections": None, "teaming": None, "ifcfg_files": None}
    f = publish("tasks/migration/network.yml", _ctx(rhel8_facts))
    assert f["disco_network"]["routes"] is None


def test_windows_ports_fallback_publishes_null():
    assert publish("tasks/windows/ports.yml", {"ansible_facts": {}}) == {"tcp_listen": None, "udp_listen": None}
    assert publish("tasks/windows/ports.yml", {"ansible_facts": {"tcp_listen": [], "udp_listen": []}}) == {}


def test_probe_output_is_never_templated():
    """Registers are untrusted data: a `{{ }}` in probe output is published literally."""
    facts = publish("tasks/linux/processes.yml", {"disco_ps": cmd("100 1 root /usr/bin/app --motd={{ 7 * 7 }}")})
    assert facts["disco_processes"][0]["command"] == "/usr/bin/app --motd={{ 7 * 7 }}"
