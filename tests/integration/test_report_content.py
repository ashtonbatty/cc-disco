#!/usr/bin/env python3
"""Integration tests that verify exported facts from container-based runs.

The container stack runs the playbook with ansible-core 2.11 against an EL6
target and with ansible-core 2.16 against EL7, EL9, EL10 and Ubuntu 24.04
targets, then exports output/facts/<host>.json. The stack is built and run
once per test session; individual tests assert against the parsed facts.

Run with:
    pytest tests/integration/test_report_content.py -v
    pytest tests/integration/test_report_content.py -v -k el9
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "tests" / "integration" / "compose.yml"
OUTPUT_DIR = REPO_ROOT / "tests" / "integration" / "output"
FACTS_DIR = OUTPUT_DIR / "facts"
# e.g. COMPOSE="podman compose" CONTAINER_CLI=podman
COMPOSE = os.environ.get("COMPOSE", "docker-compose").split()
CONTAINER_CLI = os.environ.get("CONTAINER_CLI", "docker")

MIGRATION_HOSTS = ["el6-legacy", "el7-webserver", "el7-minimal"]
INVENTORY_HOSTS = ["el9-inventory", "el10-inventory", "ubuntu2404-inventory"]
ALL_HOSTS = MIGRATION_HOSTS + INVENTORY_HOSTS
MIGRATION_FACTS = [
    "disco_platform", "disco_kernel", "disco_network", "disco_firewall", "disco_storage",
    "disco_security", "disco_identity", "disco_satellite", "disco_backup",
    "disco_filesystem", "disco_readiness", "disco_apps",
]


# ---------------------------------------------------------------------------
# Session fixture — build and run the container stack once
# ---------------------------------------------------------------------------

def _compose(*args, **kwargs):
    return subprocess.run([*COMPOSE, "-f", str(COMPOSE_FILE), *args], cwd=REPO_ROOT, **kwargs)


@pytest.fixture(scope="session")
def facts():
    """Run the container stack and return {hostname: exported facts}."""
    _compose("down", "--volumes", capture_output=True)

    result = _compose(
        "up", "--build", "--abort-on-container-exit", "--exit-code-from", "controller",
        capture_output=True, text=True, timeout=1800,
    )

    # Copy facts from the controller container before teardown. The container ID
    # depends on the compose project name, so resolve it (-a: it has exited).
    id_result = _compose("ps", "-qa", "controller", capture_output=True, text=True)
    container_id = id_result.stdout.strip().splitlines()[0] if id_result.stdout.strip() else ""
    if not container_id:
        pytest.fail(f"Could not resolve controller container ID: {id_result.stderr}")

    if FACTS_DIR.exists():
        shutil.rmtree(FACTS_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cp_result = subprocess.run(
        [CONTAINER_CLI, "cp", f"{container_id}:/home/ansible/playbook/output/facts", str(FACTS_DIR)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )

    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-60:])
        pytest.fail(f"Container stack exited with code {result.returncode}.\nLast 60 lines:\n{tail}")
    if cp_result.returncode != 0:
        pytest.fail(f"{CONTAINER_CLI} cp failed (rc={cp_result.returncode}): {cp_result.stderr}")

    loaded = {}
    for host in ALL_HOSTS:
        path = FACTS_DIR / f"{host}.json"
        assert path.exists(), f"Facts not found at {path}"
        loaded[host] = json.loads(path.read_text())
    return loaded


@pytest.fixture(scope="session")
def el6(facts):
    return facts["el6-legacy"]


@pytest.fixture(scope="session")
def el7_web(facts):
    return facts["el7-webserver"]


@pytest.fixture(scope="session")
def el7_min(facts):
    return facts["el7-minimal"]


@pytest.fixture(scope="session")
def el9(facts):
    return facts["el9-inventory"]


@pytest.fixture(scope="session")
def el10(facts):
    return facts["el10-inventory"]


@pytest.fixture(scope="session")
def ubuntu(facts):
    return facts["ubuntu2404-inventory"]


def _walk(obj, path=""):
    if isinstance(obj, dict):
        for key, val in obj.items():
            yield from _walk(val, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            yield from _walk(val, f"{path}[{i}]")
    else:
        yield path, obj


# ===========================================================================
# Every host — profile, inventory layer, null convention
# ===========================================================================

class TestEveryHost:

    @pytest.mark.parametrize("host", ALL_HOSTS)
    def test_profile(self, facts, host):
        expected = "migration" if host in MIGRATION_HOSTS else "inventory"
        controls = facts[host]["disco_controls"]
        assert controls["profile"] == expected
        assert controls["mode"] == "full"
        assert controls["omitted"] == []

    @pytest.mark.parametrize("host", ALL_HOSTS)
    def test_setup_facts_present(self, facts, host):
        assert facts[host]["hostname"] == host
        assert facts[host]["distribution"]
        assert facts[host]["memtotal_mb"] > 0

    @pytest.mark.parametrize("host", ALL_HOSTS)
    def test_packages_mirror_package_facts(self, facts, host):
        pkgs = facts[host]["packages"]
        assert isinstance(pkgs, dict) and len(pkgs) > 50
        assert "openssh-server" in pkgs
        assert isinstance(pkgs["openssh-server"], list)

    @pytest.mark.parametrize("host", ALL_HOSTS)
    def test_disco_packages_shape(self, facts, host):
        dp = facts[host]["disco_packages"]
        assert set(dp) == {"third_party", "repos", "locks", "security_updates", "snaps", "last_kernel_update"}
        assert isinstance(dp["third_party"], list)

    @pytest.mark.parametrize("host", ALL_HOSTS)
    def test_sshd_process(self, facts, host):
        procs = facts[host]["disco_processes"]
        sshd = [p for p in procs if p["name"] == "sshd"]
        assert sshd, "sshd not in process list"
        assert isinstance(sshd[0]["pid"], int)
        assert sshd[0]["user"] == "root"

    @pytest.mark.parametrize("host", ALL_HOSTS)
    def test_sshd_listening(self, facts, host):
        listeners = [p for p in facts[host]["tcp_listen"] if p["port"] == 22]
        assert listeners, "port 22 not in tcp_listen"
        assert listeners[0]["name"] == "sshd"
        assert isinstance(facts[host]["udp_listen"], list)

    @pytest.mark.parametrize("host", ALL_HOSTS)
    def test_components(self, facts, host):
        comp = facts[host]["disco_components"]
        assert set(comp) == {"openssl", "java", "python"}
        assert any(v for v in comp["python"].values()), comp["python"]

    @pytest.mark.parametrize("host", ALL_HOSTS)
    def test_no_container_runtime(self, facts, host):
        assert facts[host]["disco_containers"] is None

    @pytest.mark.parametrize("host", ALL_HOSTS)
    def test_migration_facts_only_on_migration_hosts(self, facts, host):
        present = [name for name in MIGRATION_FACTS if name in facts[host]]
        if host in MIGRATION_HOSTS:
            assert present == MIGRATION_FACTS
        else:
            assert present == []

    @pytest.mark.parametrize("host", ALL_HOSTS)
    def test_null_convention(self, facts, host):
        forbidden = {"not collected", "not configured", "not checked", "not registered",
                     "not installed", "no crontab", "not present", "n/a", "not found"}
        for name, value in facts[host].items():
            if not name.startswith("disco_"):
                continue
            for path, leaf in _walk(value, name):
                if isinstance(leaf, str):
                    assert leaf.strip().lower() not in forbidden, f"{path}: {leaf!r}"
                    assert leaf != "", f"{path}: empty string (should be null)"

    def test_redundant_probes_dropped(self, el7_web):
        # These are already provided by setup facts.
        for section, field in [("disco_storage", "lvm"), ("disco_network", "resolv_conf"),
                               ("disco_platform", "dmi_vendor"), ("disco_network", "bonding")]:
            assert field not in el7_web[section]


# ===========================================================================
# el7-webserver — feature-rich CentOS 7 (migration profile)
# ===========================================================================

class TestEl7Webserver:

    def test_sssd_conf_present(self, el7_web):
        sssd = el7_web["disco_identity"]["sssd_conf"]
        assert sssd is not None and "[sssd]" in sssd

    def test_krb5_keytab_exists(self, el7_web):
        assert el7_web["disco_identity"]["krb5_keytab_exists"] is True

    def test_nsswitch_has_sss(self, el7_web):
        assert "sss" in el7_web["disco_identity"]["nsswitch_conf"]

    def test_sudoers_drop_in_admins(self, el7_web):
        drop_ins = el7_web["disco_security"]["sudoers_drop_ins"]
        admins = next(d for d in drop_ins if "admins" in d["file"])
        assert "NOPASSWD" in admins["content"]

    def test_sshd_config_hardened(self, el7_web):
        assert "PermitRootLogin no" in el7_web["disco_security"]["sshd_config"]

    def test_pam_configs_collected(self, el7_web):
        files = [p["file"] for p in el7_web["disco_security"]["pam"]]
        assert "/etc/pam.d/sshd" in files

    def test_crypto_policy_null_on_el7(self, el7_web):
        assert el7_web["disco_security"]["crypto_policy"] is None

    def test_selinux_from_setup(self, el7_web):
        assert "selinux" in el7_web

    def test_grub_defaults_present(self, el7_web):
        assert "GRUB_TIMEOUT" in el7_web["disco_kernel"]["grub_defaults"]

    def test_fstab_has_nfs_mount(self, el7_web):
        assert "nfs" in el7_web["disco_storage"]["fstab"]

    def test_fstab_concerns_nfs(self, el7_web):
        assert any("nfs" in line for line in el7_web["disco_readiness"]["fstab_concerns"])

    def test_agents(self, el7_web):
        assert {"crowdstrike", "splunk"} <= set(el7_web["disco_backup"]["agents"])

    def test_common_apps(self, el7_web):
        assert "httpd" in el7_web["disco_apps"]["common"]

    def test_opt_directories(self, el7_web):
        opt = el7_web["disco_filesystem"]["opt"]
        assert any("splunkforwarder" in d for d in opt)
        assert any("CrowdStrike" in d for d in opt)

    def test_os_packages_not_third_party(self, el7_web):
        names = {p["name"] for p in el7_web["disco_packages"]["third_party"]}
        assert "bash" not in names and "httpd" not in names

    def test_cron_d_entry(self, el7_web):
        assert "backup-job" in el7_web["disco_readiness"]["cron_d_entries"]

    def test_alternatives_present(self, el7_web):
        assert el7_web["disco_readiness"]["alternatives"]

    def test_satellite_fields_present(self, el7_web):
        sat = el7_web["disco_satellite"]
        assert set(sat) == {"subscription_identity", "subscription_status", "rhsm_server",
                            "katello_packages", "non_satellite_repos"}


# ===========================================================================
# el7-minimal — bare CentOS 7 (migration profile)
# ===========================================================================

class TestEl7Minimal:

    def test_sssd_not_configured(self, el7_min):
        assert el7_min["disco_identity"]["sssd_conf"] is None

    def test_krb5_keytab_absent(self, el7_min):
        assert el7_min["disco_identity"]["krb5_keytab_exists"] is False

    def test_no_agents(self, el7_min):
        assert el7_min["disco_backup"]["agents"] == []

    def test_no_common_apps(self, el7_min):
        assert el7_min["disco_apps"]["common"] == []

    def test_iptables_services_deprecated(self, el7_min):
        assert "iptables-services" in el7_min["disco_readiness"]["deprecated_packages"]

    def test_no_xinetd_services(self, el7_min):
        assert el7_min["disco_readiness"]["xinetd_services"] == []

    def test_no_ifcfg_files(self, el7_min):
        assert el7_min["disco_network"]["ifcfg_files"] == []

    def test_fstab_present(self, el7_min):
        assert "centos-root" in el7_min["disco_storage"]["fstab"]


# ===========================================================================
# el6-legacy — CentOS 6, sysvinit, xinetd, ntp (ansible-core 2.11)
# ===========================================================================

class TestEl6Legacy:

    def test_release(self, el6):
        assert el6["distribution"] == "CentOS"
        assert el6["distribution_major_version"] == "6"

    def test_sysvinit_from_setup(self, el6):
        assert el6["service_mgr"] != "systemd"

    def test_crypto_policy_null_on_el6(self, el6):
        assert el6["disco_security"]["crypto_policy"] is None

    def test_pam_configs_collected(self, el6):
        assert len(el6["disco_security"]["pam"]) > 0

    def test_ifcfg_files_present(self, el6):
        assert any("ifcfg-eth0" in f for f in el6["disco_network"]["ifcfg_files"])

    def test_fstab_has_ext3(self, el6):
        assert "ext3" in el6["disco_storage"]["fstab"]
        assert any("ext3" in line for line in el6["disco_readiness"]["fstab_concerns"])

    def test_deprecated_packages(self, el6):
        assert {"ntp", "xinetd", "net-tools"} <= set(el6["disco_readiness"]["deprecated_packages"])

    def test_xinetd_services_detected(self, el6):
        assert "tftp" in el6["disco_readiness"]["xinetd_services"]

    def test_openssl_version(self, el6):
        assert "OpenSSL 1.0" in el6["disco_components"]["openssl"]

    def test_python2_version(self, el6):
        assert el6["disco_components"]["python"]["python"].startswith("Python 2.6")

    def test_alternatives_present(self, el6):
        assert el6["disco_readiness"]["alternatives"]

    def test_no_agents_or_apps(self, el6):
        assert el6["disco_backup"]["agents"] == []
        assert el6["disco_apps"]["common"] == []

    def test_ports_parsed_from_old_ss(self, el6):
        sshd = [p for p in el6["tcp_listen"] if p["port"] == 22]
        assert isinstance(sshd[0]["pid"], int)


# ===========================================================================
# Inventory-profile hosts — RHEL 9/10 and Ubuntu (ansible-core 2.16)
# ===========================================================================

class TestEl9Inventory:

    def test_distribution(self, el9):
        assert el9["distribution"] == "AlmaLinux"
        assert el9["distribution_major_version"] == "9"

    def test_epel_package_is_third_party(self, el9):
        htop = next(p for p in el9["disco_packages"]["third_party"] if p["name"] == "htop")
        assert "Fedora" in htop["vendor"]
        assert not any(p["name"] == "bash" for p in el9["disco_packages"]["third_party"])

    def test_versionlock(self, el9):
        assert any("nginx" in lock for lock in el9["disco_packages"]["locks"])

    def test_repos_from_cache(self, el9):
        repos = el9["disco_packages"]["repos"]
        assert "baseos" in repos and "epel" in repos

    def test_security_updates_is_list(self, el9):
        assert isinstance(el9["disco_packages"]["security_updates"], list)

    def test_last_kernel_update_null_without_kernel(self, el9):
        # Container images ship no kernel package.
        assert el9["disco_packages"]["last_kernel_update"] is None


class TestEl10Inventory:

    def test_distribution(self, el10):
        assert el10["distribution"] == "AlmaLinux"
        assert el10["distribution_major_version"] == "10"

    def test_python312(self, el10):
        assert el10["disco_components"]["python"]["python3"].startswith("Python 3.12")

    def test_nginx_installed(self, el10):
        assert "nginx" in el10["packages"]


class TestUbuntuInventory:

    def test_distribution(self, ubuntu):
        assert ubuntu["distribution"] == "Ubuntu"
        assert ubuntu["distribution_major_version"] == "24"

    def test_local_package_is_third_party(self, ubuntu):
        local = next(p for p in ubuntu["disco_packages"]["third_party"] if p["name"] == "disco-localtool")
        assert local["vendor"] is None
        assert not any(p["name"] == "bash" for p in ubuntu["disco_packages"]["third_party"])

    def test_held_package(self, ubuntu):
        assert "nginx" in ubuntu["disco_packages"]["locks"]

    def test_apt_sources(self, ubuntu):
        assert any("ubuntu" in line for line in ubuntu["disco_packages"]["repos"])

    def test_security_updates_is_list(self, ubuntu):
        assert isinstance(ubuntu["disco_packages"]["security_updates"], list)

    def test_services_from_sysv_fallback(self, ubuntu):
        # No systemd in the container: service_facts falls back to `service`.
        assert ubuntu["services"] is None or isinstance(ubuntu["services"], dict)
