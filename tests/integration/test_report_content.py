#!/usr/bin/env python3
"""Integration tests that verify report content from container-based runs.

These tests run the full discovery playbook against containerised EL6/EL7
targets and assert that the generated report contains the expected data.
The container stack is built and run once per test session via a session-
scoped fixture; individual tests then assert against the parsed YAML.

Run with:
    pytest tests/integration/test_report_content.py -v
    pytest tests/integration/test_report_content.py -v -k el7_webserver
"""
import os
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "tests" / "integration" / "compose.yml"
REPORT_PATH = REPO_ROOT / "tests" / "integration" / "output" / "discovery_report.yml"


# ---------------------------------------------------------------------------
# Session fixture — build and run the container stack once
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def integration_report():
    """Run the full container stack and return the parsed report dict."""
    # Tear down any stale containers/volumes
    subprocess.run(
        ["docker-compose", "-f", str(COMPOSE_FILE), "down", "--volumes"],
        cwd=REPO_ROOT,
        capture_output=True,
    )

    # Build and run
    result = subprocess.run(
        [
            "docker-compose", "-f", str(COMPOSE_FILE),
            "up", "--build",
            "--abort-on-container-exit",
            "--exit-code-from", "controller",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )

    # Copy report from the controller container before teardown
    output_dir = REPO_ROOT / "tests" / "integration" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "docker", "cp",
            "integration-controller-1:/home/ansible/playbook/output/discovery_report.yml",
            str(REPORT_PATH),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
    )

    if result.returncode != 0:
        # Print last 40 lines of output for debugging
        lines = (result.stdout + result.stderr).splitlines()
        tail = "\n".join(lines[-40:])
        pytest.fail(
            f"Container stack exited with code {result.returncode}.\n"
            f"Last 40 lines:\n{tail}"
        )

    assert REPORT_PATH.exists(), f"Report not found at {REPORT_PATH}"

    with open(REPORT_PATH) as f:
        report = yaml.safe_load(f)

    assert isinstance(report, dict), "Report root is not a dict"
    return report


# Convenience fixtures for per-host access
@pytest.fixture(scope="session")
def el6(integration_report):
    return integration_report["el6-legacy"]


@pytest.fixture(scope="session")
def el7_web(integration_report):
    return integration_report["el7-webserver"]


@pytest.fixture(scope="session")
def el7_min(integration_report):
    return integration_report["el7-minimal"]


# ===========================================================================
# Structure and metadata
# ===========================================================================

class TestReportStructure:
    """All hosts present with all sections."""

    EXPECTED_HOSTS = ["el7-webserver", "el7-minimal", "el6-legacy"]
    EXPECTED_SECTIONS = [
        "discovery_controls", "system", "cpu", "memory", "platform",
        "network", "firewall", "storage", "selinux", "security",
        "identity", "kernel", "services", "packages", "satellite",
        "agents_detected", "common_apps", "directories", "migration",
    ]

    def test_all_hosts_present(self, integration_report):
        for host in self.EXPECTED_HOSTS:
            assert host in integration_report, f"Missing host: {host}"

    @pytest.mark.parametrize("host", EXPECTED_HOSTS)
    def test_all_sections_present(self, integration_report, host):
        host_data = integration_report[host]
        for section in self.EXPECTED_SECTIONS:
            assert section in host_data, f"{host}: missing section '{section}'"

    @pytest.mark.parametrize("host", EXPECTED_HOSTS)
    def test_discovery_controls_full_mode(self, integration_report, host):
        dc = integration_report[host]["discovery_controls"]
        assert dc["mode"] == "full"
        assert dc["collect_deep_security"] is True
        assert dc["collect_deep_kernel"] is True
        assert dc["collect_deep_filesystem"] is True
        assert dc["collect_command_heavy_probes"] is True


# ===========================================================================
# el7-webserver — feature-rich CentOS 7
# ===========================================================================

class TestEl7Webserver:
    """el7-webserver: httpd, nginx, sssd, krb5, agents, cron, hardened configs."""

    # --- System ---
    def test_hostname(self, el7_web):
        assert el7_web["system"]["hostname"] == "el7-webserver"

    def test_os_version(self, el7_web):
        assert "CentOS" in el7_web["system"]["os"]
        assert el7_web["system"]["rhel_release"] == "7"

    def test_release_string(self, el7_web):
        assert "CentOS Linux release 7" in el7_web["system"]["rhel_release_string"]

    def test_uptime_is_positive(self, el7_web):
        assert el7_web["system"]["uptime_seconds"] > 0
        assert el7_web["system"]["uptime_days"] > 0

    # --- CPU / Memory ---
    def test_cpu_fields(self, el7_web):
        assert el7_web["cpu"]["physical_count"] >= 1
        assert el7_web["cpu"]["total_vcpus"] >= 1
        assert el7_web["cpu"]["model"] is not None

    def test_memory_positive(self, el7_web):
        assert el7_web["memory"]["total_mb"] > 0

    # --- Platform ---
    def test_platform_detection(self, el7_web):
        # Containers appear as bare_metal (no virt detection)
        assert el7_web["platform"]["detected_platform"] is not None
        assert el7_web["platform"]["boot_mode"] in ("UEFI", "BIOS")
        assert el7_web["platform"]["init_system"] in ("systemd", "sysvinit")

    # --- Identity ---
    def test_sssd_conf_present(self, el7_web):
        sssd = el7_web["identity"]["sssd_conf"]
        assert sssd is not None
        assert "example.com" in sssd
        assert "id_provider = ad" in sssd

    def test_krb5_keytab_exists(self, el7_web):
        assert el7_web["identity"]["krb5_keytab_exists"] is True

    def test_krb5_conf_present(self, el7_web):
        krb5 = el7_web["identity"]["krb5_conf"]
        assert krb5 is not None
        assert "EXAMPLE.COM" in krb5

    def test_nsswitch_has_sss(self, el7_web):
        nss = el7_web["identity"]["nsswitch_conf"]
        assert nss is not None
        assert "sss" in nss

    # --- Security ---
    def test_sudoers_main_present(self, el7_web):
        assert el7_web["security"]["sudoers_main"] is not None

    def test_sudoers_drop_in_admins(self, el7_web):
        drop_ins = el7_web["security"]["sudoers_drop_ins"]
        assert isinstance(drop_ins, list)
        # Should have at least the admins file (plus the ansible test user file)
        paths = [d["file"] for d in drop_ins]
        assert any("admins" in p for p in paths), f"Expected admins drop-in, got {paths}"
        # Verify content
        admins = next(d for d in drop_ins if "admins" in d["file"])
        assert "NOPASSWD" in admins["content"]

    def test_sshd_config_hardened(self, el7_web):
        sshd = el7_web["security"]["sshd_config"]
        assert sshd is not None
        assert "PermitRootLogin no" in sshd
        assert "PasswordAuthentication no" in sshd

    def test_pam_configs_collected(self, el7_web):
        pam = el7_web["security"]["pam"]
        assert isinstance(pam, list)
        assert len(pam) > 0
        pam_files = [p["file"] for p in pam]
        assert any("system-auth" in f for f in pam_files)

    def test_crypto_policy_null_on_el7(self, el7_web):
        # crypto-policies is RHEL 8+
        assert el7_web["security"]["crypto_policy"] is None

    # --- SELinux ---
    def test_selinux_config_present(self, el7_web):
        config = el7_web["selinux"]["config"]
        assert config is not None
        assert "SELINUX=enforcing" in config

    # --- Kernel ---
    def test_loaded_modules_present(self, el7_web):
        assert el7_web["kernel"]["loaded_modules"] is not None

    def test_grub_defaults_present(self, el7_web):
        grub = el7_web["kernel"]["grub_defaults"]
        assert grub is not None
        assert "GRUB_TIMEOUT" in grub
        assert "crashkernel" in grub

    # --- Network ---
    def test_has_ip_addresses(self, el7_web):
        # Containers running sshd -D (no systemd) may not populate
        # default_ipv4 — check all_ipv4_addresses instead
        addrs = el7_web["network"]["all_ipv4_addresses"]
        assert isinstance(addrs, list)

    def test_resolv_conf_present(self, el7_web):
        resolv = el7_web["network"]["resolv_conf"]
        assert resolv is not None
        assert "nameserver" in resolv

    # --- Firewall ---
    def test_firewall_fields_present(self, el7_web):
        fw = el7_web["firewall"]
        assert "firewalld_active" in fw
        assert "iptables_active" in fw
        assert "firewalld_zones" in fw
        assert "nftables_rules" in fw

    # --- Storage ---
    def test_fstab_has_nfs_mount(self, el7_web):
        fstab = el7_web["storage"]["fstab"]
        assert fstab is not None
        assert "nfs-server:/exports/data" in fstab

    def test_mounts_populated(self, el7_web):
        mounts = el7_web["storage"]["mounts"]
        assert isinstance(mounts, list)
        assert len(mounts) > 0
        # Each mount should have required fields
        for m in mounts:
            assert "device" in m
            assert "mount" in m
            assert "fstype" in m

    # --- Packages ---
    def test_package_count_positive(self, el7_web):
        assert el7_web["packages"]["total_count"] > 100

    def test_non_redhat_packages_list(self, el7_web):
        pkgs = el7_web["packages"]["non_redhat_packages"]
        assert isinstance(pkgs, list)
        # CentOS packages are not Red Hat vendor
        assert len(pkgs) > 0

    # --- Agents ---
    def test_crowdstrike_detected(self, el7_web):
        agents = el7_web["agents_detected"]
        assert isinstance(agents, list)
        assert "crowdstrike" in agents

    def test_splunk_detected(self, el7_web):
        agents = el7_web["agents_detected"]
        assert "splunk" in agents

    # --- Common Apps ---
    def test_httpd_in_common_apps(self, el7_web):
        apps = el7_web["common_apps"]
        assert isinstance(apps, list)
        assert "httpd" in apps

    # --- Filesystem ---
    def test_opt_directories(self, el7_web):
        opt = el7_web["directories"]["opt"]
        assert isinstance(opt, list)
        opt_basenames = [os.path.basename(p) for p in opt]
        assert "CrowdStrike" in opt_basenames
        assert "splunkforwarder" in opt_basenames

    # --- Migration ---
    def test_deprecated_packages(self, el7_web):
        deprecated = el7_web["migration"]["deprecated_packages"]
        assert isinstance(deprecated, list)
        assert "net-tools" in deprecated

    def test_python_versions_present(self, el7_web):
        pyver = el7_web["migration"]["python_versions"]
        assert pyver is not None
        assert "python" in pyver.lower()

    def test_fstab_concerns_nfs(self, el7_web):
        concerns = el7_web["migration"]["fstab_concerns"]
        assert concerns is not None
        assert "nfs" in concerns

    def test_alternatives_present(self, el7_web):
        alts = el7_web["migration"]["alternatives"]
        assert alts is not None
        assert len(alts.strip()) > 0

    # --- Satellite ---
    def test_satellite_fields_present(self, el7_web):
        sat = el7_web["satellite"]
        assert "subscription_identity" in sat
        assert "subscription_status" in sat
        assert "satellite_server" in sat


# ===========================================================================
# el7-minimal — bare CentOS 7, iptables only
# ===========================================================================

class TestEl7Minimal:
    """el7-minimal: bare CentOS 7 with iptables-services, no extras."""

    def test_hostname(self, el7_min):
        assert el7_min["system"]["hostname"] == "el7-minimal"

    def test_os_version(self, el7_min):
        assert el7_min["system"]["rhel_release"] == "7"

    # --- Identity: nothing configured ---
    def test_sssd_not_configured(self, el7_min):
        assert el7_min["identity"]["sssd_conf"] is None

    def test_krb5_keytab_absent(self, el7_min):
        assert el7_min["identity"]["krb5_keytab_exists"] is False

    # --- Security ---
    def test_crypto_policy_null_on_el7(self, el7_min):
        assert el7_min["security"]["crypto_policy"] is None

    # --- SELinux: not configured in container ---
    def test_selinux_config_null(self, el7_min):
        assert el7_min["selinux"]["config"] is None

    # --- Kernel ---
    def test_grub_defaults_null(self, el7_min):
        # No /etc/default/grub in minimal container
        assert el7_min["kernel"]["grub_defaults"] is None

    # --- Agents: none installed ---
    def test_no_agents(self, el7_min):
        assert el7_min["agents_detected"] == []

    # --- Common apps: none ---
    def test_no_common_apps(self, el7_min):
        assert el7_min["common_apps"] == []

    # --- Migration ---
    def test_iptables_services_deprecated(self, el7_min):
        deprecated = el7_min["migration"]["deprecated_packages"]
        assert isinstance(deprecated, list)
        assert "iptables-services" in deprecated

    def test_no_xinetd_services(self, el7_min):
        assert el7_min["migration"]["xinetd_services"] == []

    # --- Network ---
    def test_no_ifcfg_files(self, el7_min):
        assert el7_min["network"]["ifcfg_files"] == []

    def test_nm_not_found(self, el7_min):
        assert el7_min["network"]["networkmanager_active"] == "not found"

    # --- Filesystem: no extra dirs ---
    def test_opt_empty(self, el7_min):
        assert el7_min["directories"]["opt"] == []

    # --- Storage ---
    def test_fstab_present(self, el7_min):
        fstab = el7_min["storage"]["fstab"]
        assert fstab is not None
        assert "centos-root" in fstab


# ===========================================================================
# el6-legacy — CentOS 6, sysvinit, xinetd, ntp
# ===========================================================================

class TestEl6Legacy:
    """el6-legacy: CentOS 6 with sysvinit, xinetd, ntp, legacy networking."""

    def test_hostname(self, el6):
        assert el6["system"]["hostname"] == "el6-legacy"

    def test_os_version(self, el6):
        assert "CentOS" in el6["system"]["os"]
        assert el6["system"]["rhel_release"] == "6"

    def test_release_string(self, el6):
        assert "CentOS release 6" in el6["system"]["rhel_release_string"]

    # --- Platform ---
    def test_init_system_sysvinit(self, el6):
        assert el6["platform"]["init_system"] == "sysvinit"

    # --- Identity: nothing configured ---
    def test_sssd_not_configured(self, el6):
        assert el6["identity"]["sssd_conf"] is None

    def test_krb5_keytab_absent(self, el6):
        assert el6["identity"]["krb5_keytab_exists"] is False

    # --- Security ---
    def test_crypto_policy_null_on_el6(self, el6):
        # crypto-policies is RHEL 8+
        assert el6["security"]["crypto_policy"] is None

    def test_pam_configs_collected(self, el6):
        pam = el6["security"]["pam"]
        assert isinstance(pam, list)
        assert len(pam) > 0

    # --- Network ---
    def test_ifcfg_files_present(self, el6):
        ifcfg = el6["network"]["ifcfg_files"]
        assert isinstance(ifcfg, list)
        assert any("ifcfg-eth0" in f for f in ifcfg)

    def test_nm_not_found(self, el6):
        assert el6["network"]["networkmanager_active"] == "not found"

    # --- Storage ---
    def test_fstab_has_ext3(self, el6):
        fstab = el6["storage"]["fstab"]
        assert fstab is not None
        assert "ext3" in fstab

    # --- Migration: deprecated packages ---
    def test_ntp_deprecated(self, el6):
        deprecated = el6["migration"]["deprecated_packages"]
        assert "ntp" in deprecated

    def test_xinetd_deprecated(self, el6):
        deprecated = el6["migration"]["deprecated_packages"]
        assert "xinetd" in deprecated

    def test_net_tools_deprecated(self, el6):
        deprecated = el6["migration"]["deprecated_packages"]
        assert "net-tools" in deprecated

    # --- Migration: xinetd services ---
    def test_xinetd_services_detected(self, el6):
        xinetd = el6["migration"]["xinetd_services"]
        assert isinstance(xinetd, list)
        assert len(xinetd) > 0
        assert "tftp" in xinetd

    # --- Migration: legacy network ---
    def test_legacy_network_ifcfg_count(self, el6):
        legacy = el6["migration"]["legacy_network"]
        assert legacy is not None
        assert "ifcfg_count:" in legacy
        # Should have at least eth0 + lo
        assert "ifcfg_count:0" not in legacy

    # --- Migration: OpenSSL ---
    def test_openssl_version_present(self, el6):
        openssl = el6["migration"]["openssl_version"]
        assert openssl is not None
        assert "OpenSSL 1.0" in openssl

    # --- Migration: alternatives ---
    def test_alternatives_present(self, el6):
        alts = el6["migration"]["alternatives"]
        assert alts is not None
        assert len(alts.strip()) > 0

    # --- Migration: fstab concerns ---
    def test_fstab_concerns_ext3(self, el6):
        concerns = el6["migration"]["fstab_concerns"]
        assert concerns is not None
        assert "ext3" in concerns

    # --- Agents: none ---
    def test_no_agents(self, el6):
        assert el6["agents_detected"] == []

    # --- Common apps: none ---
    def test_no_common_apps(self, el6):
        assert el6["common_apps"] == []

    # --- Filesystem: no /opt contents ---
    def test_opt_empty(self, el6):
        assert el6["directories"]["opt"] == []

    # --- Packages ---
    def test_package_count_positive(self, el6):
        assert el6["packages"]["total_count"] > 50


# ===========================================================================
# Cross-host consistency checks
# ===========================================================================

class TestCrossHost:
    """Assertions that should hold true across all hosts."""

    HOSTS = ["el6-legacy", "el7-minimal", "el7-webserver"]

    @pytest.mark.parametrize("host", HOSTS)
    def test_no_forbidden_placeholders(self, integration_report, host):
        """No English placeholder strings in template-controlled fields."""
        forbidden = [
            "not collected", "not configured", "not checked",
            "not registered", "not installed", "no crontab",
            "not present", "N/A", "N/A (pre-RHEL 8)",
        ]
        for path, value in _walk_values(integration_report[host]):
            if isinstance(value, str):
                lower = value.strip().lower()
                for placeholder in forbidden:
                    assert lower != placeholder.lower(), (
                        f"{host}{path}: forbidden placeholder '{placeholder}' "
                        f"(got {value!r})"
                    )

    @pytest.mark.parametrize("host", HOSTS)
    def test_list_fields_are_lists(self, integration_report, host):
        """Fields that must always be lists should never be strings or null."""
        host_data = integration_report[host]
        list_checks = [
            ("network", "all_ipv4_addresses"),
            ("network", "all_ipv6_addresses"),
            ("network", "dns_nameservers"),
            ("network", "dns_search"),
            ("network", "interfaces"),
            ("network", "ifcfg_files"),
            ("security", "sudoers_drop_ins"),
            ("security", "pam"),
            ("kernel", "third_party_modules"),
            ("kernel", "deprecated_modules"),
            ("packages", "non_redhat_packages"),
            ("migration", "deprecated_packages"),
            ("migration", "java_packages"),
            ("migration", "xinetd_services"),
            ("migration", "cron_d_entries"),
            ("storage", "mounts"),
        ]
        for section, field in list_checks:
            value = host_data.get(section, {}).get(field)
            assert isinstance(value, list), (
                f"{host}.{section}.{field} should be list, "
                f"got {type(value).__name__}: {value!r}"
            )

        for field in ("agents_detected", "common_apps"):
            value = host_data.get(field)
            assert isinstance(value, list), (
                f"{host}.{field} should be list, "
                f"got {type(value).__name__}: {value!r}"
            )

    @pytest.mark.parametrize("host", HOSTS)
    def test_numeric_fields_are_numbers(self, integration_report, host):
        host_data = integration_report[host]
        assert isinstance(host_data["system"]["uptime_seconds"], int)
        assert isinstance(host_data["system"]["uptime_days"], (int, float))
        assert isinstance(host_data["cpu"]["physical_count"], int)
        assert isinstance(host_data["cpu"]["total_vcpus"], int)
        assert isinstance(host_data["memory"]["total_mb"], int)
        assert isinstance(host_data["packages"]["total_count"], int)
        assert isinstance(host_data["migration"]["packages_32bit_count"], int)

    @pytest.mark.parametrize("host", HOSTS)
    def test_boolean_fields_are_booleans(self, integration_report, host):
        host_data = integration_report[host]
        assert isinstance(host_data["identity"]["krb5_keytab_exists"], bool)

    @pytest.mark.parametrize("host", HOSTS)
    def test_python_versions_present(self, integration_report, host):
        """All hosts should report Python versions."""
        pyver = integration_report[host]["migration"]["python_versions"]
        assert pyver is not None
        assert "python" in pyver.lower()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _walk_values(obj, path=""):
    """Yield (path, value) for every leaf value in a nested dict/list."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            yield from _walk_values(val, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            yield from _walk_values(val, f"{path}[{i}]")
    else:
        yield path, obj
