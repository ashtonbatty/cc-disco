"""Fixtures and Jinja2 environment for template testing."""
import base64
import json
import os
import re

import jinja2
import pytest
import yaml


# ---------------------------------------------------------------------------
# Jinja2 environment that mimics Ansible's template rendering
# ---------------------------------------------------------------------------

def _b64encode(value):
    """Encode a string to base64 (for building test fixtures)."""
    return base64.b64encode(value.encode()).decode()


def _b64decode(value):
    """Ansible b64decode filter."""
    if not value:
        return ""
    return base64.b64decode(value).decode()


def _to_json(value):
    """Ansible to_json filter."""
    return json.dumps(value)


def _basename(value):
    """Ansible basename filter."""
    return os.path.basename(value)


def _bool(value):
    """Ansible bool filter — coerce to Python bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "yes", "1")
    return bool(value)


def _comment(value):
    """Ansible comment filter — wraps text in # comment lines."""
    return "\n".join(f"# {line}" for line in value.splitlines())


def _difference(a, b):
    """Ansible difference filter — returns items in a but not in b."""
    return [x for x in a if x not in b]


def _search(value, pattern):
    """Ansible search test — regex search on string."""
    if value is None:
        return False
    return bool(re.search(pattern, str(value)))


def _match(value, pattern):
    """Ansible match test — regex match (anchored) on string."""
    if value is None:
        return False
    return bool(re.match(pattern, str(value)))


@pytest.fixture(scope="session")
def jinja_env():
    """Create a Jinja2 environment that mirrors Ansible's template rendering."""
    templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_dir),
        undefined=jinja2.Undefined,
        keep_trailing_newline=True,
    )
    env.filters["b64decode"] = _b64decode
    env.filters["bool"] = _bool
    env.filters["to_json"] = _to_json
    env.filters["basename"] = _basename
    env.filters["comment"] = _comment
    env.filters["difference"] = _difference
    env.tests["search"] = _search
    env.tests["match"] = _match
    return env


# ---------------------------------------------------------------------------
# Helper to build Ansible-shaped registered variable dicts
# ---------------------------------------------------------------------------

def _cmd_result(stdout="", rc=0):
    """Build a dict shaped like an Ansible registered command result."""
    return {
        "stdout": stdout,
        "stdout_lines": stdout.splitlines() if stdout else [],
        "rc": rc,
        "changed": False,
    }


def _slurp_result(content=""):
    """Build a dict shaped like an Ansible slurp result."""
    return {"content": _b64encode(content) if content else ""}


def _find_result(files=None):
    """Build a dict shaped like an Ansible find result."""
    file_list = files or []
    return {
        "files": [{"path": f} for f in file_list],
        "matched": len(file_list),
    }


def _stat_result(exists=True):
    """Build a dict shaped like an Ansible stat result."""
    return {"stat": {"exists": exists}}


def _uri_result(status=200):
    """Build a dict shaped like an Ansible uri result."""
    return {"status": status}


# ---------------------------------------------------------------------------
# Mock hostvars fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def full_hostvars():
    """Complete hostvars simulating a typical RHEL 8 server.

    Every disco_* variable is populated with realistic data.
    """
    return {
        # --- Ansible gather_facts ---
        "ansible_hostname": "rhel8-web01",
        "ansible_fqdn": "rhel8-web01.example.com",
        "ansible_distribution": "RedHat",
        "ansible_distribution_version": "8.6",
        "ansible_distribution_major_version": "8",
        "ansible_kernel": "4.18.0-372.el8.x86_64",
        "ansible_architecture": "x86_64",
        "ansible_uptime_seconds": 864000,
        "ansible_processor": ["0", "GenuineIntel", "Intel(R) Xeon(R) Gold 6248 CPU @ 2.50GHz"],
        "ansible_processor_count": 2,
        "ansible_processor_cores": 20,
        "ansible_processor_vcpus": 80,
        "ansible_memtotal_mb": 65536,
        "ansible_swaptotal_mb": 4096,
        "ansible_service_mgr": "systemd",
        "ansible_default_ipv4": {
            "address": "10.0.1.50",
            "gateway": "10.0.1.1",
        },
        "ansible_all_ipv4_addresses": ["10.0.1.50", "10.0.1.51"],
        "ansible_all_ipv6_addresses": ["fe80::1"],
        "ansible_dns": {
            "nameservers": ["10.0.0.2", "10.0.0.3"],
            "search": ["example.com"],
        },
        "ansible_interfaces": ["eth0", "lo"],
        "ansible_eth0": {
            "ipv4": {"address": "10.0.1.50"},
            "macaddress": "00:50:56:a1:b2:c3",
            "type": "ether",
            "active": True,
        },
        "ansible_lo": {
            "ipv4": {"address": "127.0.0.1"},
            "macaddress": "00:00:00:00:00:00",
            "type": "loopback",
            "active": True,
        },
        "ansible_mounts": [
            {
                "device": "/dev/sda1",
                "mount": "/",
                "fstype": "xfs",
                "size_total": 53687091200,
                "size_available": 32212254720,
                "options": "rw,relatime",
            },
        ],
        "ansible_date_time": {"iso8601": "2026-03-08T12:00:00Z"},
        "ansible_facts": {
            "services": {
                "firewalld.service": {"state": "running", "status": "enabled"},
                "NetworkManager.service": {"state": "running", "status": "enabled"},
                "sshd.service": {"state": "running", "status": "enabled"},
                "chronyd.service": {"state": "running", "status": "enabled"},
            },
            "packages": {
                "bash": [{"version": "4.4.20", "release": "4.el8", "arch": "x86_64", "vendor": "Red Hat, Inc."}],
                "nginx": [{"version": "1.20.1", "release": "1.el8", "arch": "x86_64", "vendor": "Fedora Project"}],
                "ntp": [{"version": "4.2.8", "release": "1.el8", "arch": "x86_64", "vendor": "Red Hat, Inc."}],
            },
        },
        # --- disco_* registered variables ---
        "disco_redhat_release": _slurp_result("Red Hat Enterprise Linux release 8.6 (Ootpa)"),
        "disco_selinux_status": _cmd_result("SELinux status: enforcing"),
        "disco_selinux_config": _slurp_result("SELINUX=enforcing\nSELINUXTYPE=targeted"),
        "disco_sssd_conf": _slurp_result("[sssd]\ndomains = example.com"),
        "disco_realm_list": _cmd_result("example.com\n  type: kerberos"),
        "disco_krb5_conf": _slurp_result("[libdefaults]\ndefault_realm = EXAMPLE.COM"),
        "disco_krb5_keytab": _stat_result(True),
        "disco_nsswitch_conf": _slurp_result("passwd: files sss\ngroup: files sss"),
        "disco_sudoers_main": _slurp_result("root ALL=(ALL) ALL"),
        "disco_sudoers_d_files": _find_result(["/etc/sudoers.d/admins"]),
        "disco_sudoers_d_contents": {
            "results": [
                {
                    "content": _b64encode("%admins ALL=(ALL) NOPASSWD: ALL"),
                    "item": {"path": "/etc/sudoers.d/admins"},
                }
            ]
        },
        "disco_sshd_config": _slurp_result("PermitRootLogin no\nPasswordAuthentication no"),
        "disco_sshd_d_contents": {
            "results": [
                {
                    "content": _b64encode("Match Group developers\n  AllowTcpForwarding yes"),
                    "item": {"path": "/etc/ssh/sshd_config.d/50-developers.conf"},
                }
            ]
        },
        "disco_pam_contents": {
            "results": [
                {
                    "content": _b64encode("auth required pam_env.so"),
                    "item": "/etc/pam.d/system-auth",
                }
            ]
        },
        "disco_crypto_policy": _cmd_result("DEFAULT"),
        "disco_dmi_vendor": _slurp_result("VMware, Inc."),
        "disco_dmi_product": _slurp_result("VMware Virtual Platform"),
        "disco_ec2_check": _uri_result(0),
        "disco_azure_check": _uri_result(0),
        "disco_virt_type": _cmd_result("vmware"),
        "disco_virt_what": _cmd_result("vmware"),
        "disco_efi_dir": _stat_result(True),
        "disco_init_system": "systemd",
        "disco_routes": _cmd_result("default via 10.0.1.1 dev eth0\n10.0.1.0/24 dev eth0 proto kernel"),
        "disco_nm_active": "running",
        "disco_nmcli_connections": _cmd_result("eth0:uuid1:802-3-ethernet:eth0"),
        "disco_bond_files": _find_result([]),
        "disco_bond_interfaces": "",
        "disco_team_details": _cmd_result(""),
        "disco_ifcfg_files": _find_result(["/etc/sysconfig/network-scripts/ifcfg-eth0"]),
        "disco_firewalld_active": "running",
        "disco_firewalld_zones": _cmd_result("public (active)\n  services: ssh dhcpv6-client"),
        "disco_iptables_active": _cmd_result("inactive"),
        "disco_iptables_rules": _cmd_result("Chain INPUT (policy ACCEPT)"),
        "disco_lsmod": _cmd_result("Module                  Size  Used by\nvmw_balloon            20480  0"),
        "disco_third_party_modules": _cmd_result("vmw_balloon|extra/vmw_balloon.ko|VMware, Inc."),
        "disco_last_kernel_update": _cmd_result("kernel-4.18.0-372.el8.x86_64  Mon 01 Jan 2024"),
        "disco_grub_defaults": _slurp_result("GRUB_TIMEOUT=5\nGRUB_DEFAULT=saved"),
        "disco_deprecated_modules": _cmd_result(""),
        "disco_systemd_enabled": "sshd.service\nchronyd.service\nfirewalld.service",
        "disco_systemd_running": "sshd.service\nchronyd.service",
        "disco_tuned_profile": _cmd_result("Current active profile: virtual-guest"),
        "disco_pvs": _cmd_result("  /dev/sda2  rhel  50.00  10.00"),
        "disco_vgs": _cmd_result("  rhel  50.00  10.00  3  1"),
        "disco_lvs": _cmd_result("  root  rhel  30.00  -wi-ao----\n  swap  rhel  4.00  -wi-ao----"),
        "disco_df": "/|xfs|/dev/sda1|53687091200|32212254720",
        "disco_lsblk": _cmd_result("sda    50G disk\nsda1   50G part xfs    /"),
        "disco_fstab": _slurp_result("/dev/sda1 / xfs defaults 0 0"),
        "disco_multipath": _cmd_result(""),
        "disco_nfs_mounts": "",
        "disco_pkg_count": "850",
        "disco_non_rh_packages": ["nginx|Fedora Project|1.20.1-1.el8.x86_64"],
        "disco_versionlocks": _cmd_result(""),
        "disco_repos_enabled": _cmd_result("rhel-8-for-x86_64-baseos-rpms\nrhel-8-for-x86_64-appstream-rpms"),
        "disco_non_satellite_repos": _cmd_result(""),
        "disco_backup_monitoring": _cmd_result("crowdstrike\nsplunk"),
        "disco_sub_identity": _cmd_result("system identity: 12345-abcde"),
        "disco_sub_status": _cmd_result("Overall Status: Current"),
        "disco_satellite_server": _cmd_result("hostname = satellite.example.com"),
        "disco_katello_info": _cmd_result("katello-host-tools-4.0.0"),
        "disco_opt_listing": _find_result(["/opt/splunkforwarder", "/opt/CrowdStrike"]),
        "disco_data_listing": _find_result([]),
        "disco_third_party_paths": _cmd_result("=== /usr/local/bin ===\ncustom-tool"),
        "disco_python_versions": _cmd_result("python:not found\npython3:Python 3.6.8\nplatform-python:Python 3.6.8"),
        "disco_32bit_packages": [],
        "disco_deprecated_packages": ["ntp"],
        "disco_time_services": "ntpd:not found\nchronyd:running",
        "disco_xinetd": _find_result([]),
        "disco_legacy_network": "ifcfg_count:1,nm_status:running",
        "disco_fstab_concerns": _cmd_result(""),
        "disco_openssl_version": _cmd_result("OpenSSL 1.1.1k  FIPS 25 Mar 2021"),
        "disco_root_crontab": _cmd_result("0 2 * * * /usr/local/bin/backup.sh"),
        "disco_system_crontab": _slurp_result("SHELL=/bin/bash\n0 * * * * root run-parts /etc/cron.hourly"),
        "disco_cron_d": _find_result(["/etc/cron.d/0hourly"]),
        "disco_common_apps": ["nginx"],
        # Discovery controls (persisted via set_fact)
        "disco_discovery_mode": "full",
        "disco_collect_deep_security": True,
        "disco_collect_deep_kernel": True,
        "disco_collect_deep_filesystem": True,
        "disco_collect_command_heavy_probes": True,
    }


@pytest.fixture(scope="session")
def minimal_hostvars():
    """Hostvars where most disco_* variables have empty/missing data.

    Simulates a host where many tasks returned empty results or were skipped.
    """
    return {
        "ansible_hostname": "rhel7-minimal",
        "ansible_fqdn": "rhel7-minimal.example.com",
        "ansible_distribution": "RedHat",
        "ansible_distribution_version": "7.9",
        "ansible_distribution_major_version": "7",
        "ansible_kernel": "3.10.0-1160.el7.x86_64",
        "ansible_architecture": "x86_64",
        "ansible_uptime_seconds": 3600,
        "ansible_processor": ["0", "GenuineIntel"],
        "ansible_processor_count": 1,
        "ansible_processor_cores": 1,
        "ansible_processor_vcpus": 1,
        "ansible_memtotal_mb": 2048,
        "ansible_swaptotal_mb": 0,
        "ansible_service_mgr": "systemd",
        "ansible_default_ipv4": {},
        "ansible_all_ipv4_addresses": [],
        "ansible_all_ipv6_addresses": [],
        "ansible_dns": {},
        "ansible_interfaces": [],
        "ansible_mounts": [],
        "ansible_date_time": {"iso8601": "2026-03-08T12:00:00Z"},
        "ansible_facts": {"services": {}, "packages": {}},
        # All disco_* with empty results
        "disco_redhat_release": _slurp_result(""),
        "disco_selinux_status": _cmd_result(""),
        "disco_selinux_config": _slurp_result(""),
        "disco_sssd_conf": _slurp_result(""),
        "disco_realm_list": _cmd_result(""),
        "disco_krb5_conf": _slurp_result(""),
        "disco_krb5_keytab": _stat_result(False),
        "disco_nsswitch_conf": _slurp_result(""),
        "disco_sudoers_main": _slurp_result(""),
        "disco_sudoers_d_files": _find_result([]),
        "disco_sudoers_d_contents": {"results": []},
        "disco_sshd_config": _slurp_result(""),
        "disco_sshd_d_contents": {"results": []},
        "disco_pam_contents": {"results": []},
        "disco_dmi_vendor": _slurp_result(""),
        "disco_dmi_product": _slurp_result(""),
        "disco_ec2_check": _uri_result(0),
        "disco_azure_check": _uri_result(0),
        "disco_virt_type": _cmd_result(""),
        "disco_virt_what": _cmd_result(""),
        "disco_efi_dir": _stat_result(False),
        "disco_init_system": "systemd",
        "disco_routes": _cmd_result(""),
        "disco_nm_active": "",
        "disco_nmcli_connections": _cmd_result(""),
        "disco_bond_files": _find_result([]),
        "disco_bond_interfaces": "",
        "disco_team_details": _cmd_result(""),
        "disco_ifcfg_files": _find_result([]),
        "disco_firewalld_active": "",
        "disco_iptables_active": _cmd_result(""),
        "disco_iptables_rules": _cmd_result(""),
        "disco_lsmod": _cmd_result(""),
        "disco_third_party_modules": _cmd_result(""),
        "disco_last_kernel_update": _cmd_result(""),
        "disco_grub_defaults": _slurp_result(""),
        "disco_deprecated_modules": _cmd_result(""),
        "disco_systemd_enabled": "",
        "disco_systemd_running": "",
        "disco_tuned_profile": _cmd_result(""),
        "disco_pvs": _cmd_result(""),
        "disco_vgs": _cmd_result(""),
        "disco_lvs": _cmd_result(""),
        "disco_df": "",
        "disco_lsblk": _cmd_result(""),
        "disco_fstab": _slurp_result(""),
        "disco_multipath": _cmd_result(""),
        "disco_nfs_mounts": "",
        "disco_pkg_count": "0",
        "disco_non_rh_packages": [],
        "disco_versionlocks": _cmd_result(""),
        "disco_repos_enabled": _cmd_result(""),
        "disco_non_satellite_repos": _cmd_result(""),
        "disco_backup_monitoring": _cmd_result(""),
        "disco_sub_identity": _cmd_result(""),
        "disco_sub_status": _cmd_result(""),
        "disco_satellite_server": _cmd_result(""),
        "disco_katello_info": _cmd_result(""),
        "disco_opt_listing": _find_result([]),
        "disco_data_listing": _find_result([]),
        "disco_third_party_paths": _cmd_result(""),
        "disco_python_versions": _cmd_result(""),
        "disco_32bit_packages": [],
        "disco_deprecated_packages": [],
        "disco_time_services": "",
        "disco_xinetd": _find_result([]),
        "disco_legacy_network": "",
        "disco_fstab_concerns": _cmd_result(""),
        "disco_openssl_version": _cmd_result(""),
        "disco_root_crontab": _cmd_result(""),
        "disco_system_crontab": _slurp_result(""),
        "disco_cron_d": _find_result([]),
        "disco_common_apps": [],
        # Discovery controls (persisted via set_fact)
        "disco_discovery_mode": "full",
        "disco_collect_deep_security": True,
        "disco_collect_deep_kernel": True,
        "disco_collect_deep_filesystem": True,
        "disco_collect_command_heavy_probes": True,
    }


def render_report(jinja_env, hostvars_dict, hostname="testhost.example.com"):
    """Render the report template with the given hostvars and return the YAML string."""
    template = jinja_env.get_template("report.yml.j2")
    context = {
        "ansible_managed": "Ansible managed",
        "hostvars": {hostname: hostvars_dict},
        "report_hosts": [hostname],
        "groups": {"all": [hostname]},
    }
    return template.render(**context)


@pytest.fixture(scope="session")
def full_report_yaml(jinja_env, full_hostvars):
    """Rendered YAML string from full_hostvars."""
    return render_report(jinja_env, full_hostvars)


@pytest.fixture(scope="session")
def minimal_report_yaml(jinja_env, minimal_hostvars):
    """Rendered YAML string from minimal_hostvars."""
    return render_report(jinja_env, minimal_hostvars)


@pytest.fixture(scope="session")
def full_report(full_report_yaml):
    """Parsed report dict from full_hostvars."""
    return yaml.safe_load(full_report_yaml)


@pytest.fixture(scope="session")
def minimal_report(minimal_report_yaml):
    """Parsed report dict from minimal_hostvars."""
    return yaml.safe_load(minimal_report_yaml)
