#!/usr/bin/env python3
"""Validate the integration run's exported facts (output/facts/<host>.json).

Checks:
1. Every expected host has a facts file that parses as a JSON object
2. The profile matches the host's OS, and only extended hosts carry extended facts
3. The inventory layer is present on every host (packages, processes, sshd on :22, ...)
4. No placeholder strings or empty strings stand in for null in disco_* facts
5. A few scenario-specific assertions

Uses only the standard library so it runs on any controller Python.
"""
import json
import sys
from pathlib import Path


# disco_profile=extended is set for every host; only the RHEL-family ones take it.
EXTENDED_HOSTS = ["el6-legacy", "el7-webserver", "el7-minimal", "el9-extended", "el10-extended"]
INVENTORY_HOSTS = ["ubuntu2404-inventory"]
EXPECTED_HOSTS = EXTENDED_HOSTS + INVENTORY_HOSTS

EXTENDED_FACTS = [
    "disco_platform", "disco_kernel", "disco_network", "disco_firewall", "disco_storage",
    "disco_security", "disco_identity", "disco_satellite", "disco_backup",
    "disco_filesystem", "disco_readiness", "disco_apps",
]
INVENTORY_FACTS = [
    "disco_controls", "disco_packages", "disco_processes", "disco_components",
    "disco_containers", "packages", "services", "tcp_listen", "udp_listen",
]

FORBIDDEN_PLACEHOLDERS = {
    "not collected", "not configured", "not checked", "not registered",
    "not installed", "no crontab", "not present", "n/a", "not found",
}


def walk(obj, path=""):
    if isinstance(obj, dict):
        for key, val in obj.items():
            yield from walk(val, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            yield from walk(val, f"{path}[{i}]")
    else:
        yield path, obj


def check_host(host, facts):
    errors = []
    expected_profile = "extended" if host in EXTENDED_HOSTS else "inventory"

    profile = (facts.get("disco_controls") or {}).get("profile")
    if profile != expected_profile:
        errors.append(f"{host}: profile {profile!r}, expected {expected_profile!r}")

    for name in INVENTORY_FACTS:
        if name not in facts:
            errors.append(f"{host}: missing inventory fact {name}")

    for name in EXTENDED_FACTS:
        if expected_profile == "extended" and name not in facts:
            errors.append(f"{host}: missing extended fact {name}")
        if expected_profile == "inventory" and name in facts:
            errors.append(f"{host}: unexpected extended fact {name}")

    if not facts.get("packages"):
        errors.append(f"{host}: packages is empty")
    procs = facts.get("disco_processes") or []
    if not any(p.get("name") == "sshd" for p in procs):
        errors.append(f"{host}: no sshd in disco_processes")
    listen = facts.get("tcp_listen") or []
    if not any(p.get("port") == 22 for p in listen):
        errors.append(f"{host}: port 22 missing from tcp_listen")

    for name, value in facts.items():
        if not name.startswith("disco_"):
            continue
        for path, leaf in walk(value, name):
            if isinstance(leaf, str) and leaf.strip().lower() in FORBIDDEN_PLACEHOLDERS:
                errors.append(f"{host}: placeholder {leaf!r} at {path}")
            if leaf == "":
                errors.append(f"{host}: empty string at {path} (should be null)")
    return errors


def check_scenarios(hosts):
    errors = []
    web = hosts.get("el7-webserver", {})
    agents = (web.get("disco_backup") or {}).get("agents") or []
    for agent in ("crowdstrike", "splunk"):
        if agent not in agents:
            errors.append(f"el7-webserver: agent {agent!r} not detected, got {agents}")
    if "httpd" not in ((web.get("disco_apps") or {}).get("common") or []):
        errors.append("el7-webserver: httpd missing from disco_apps.common")

    el6 = hosts.get("el6-legacy", {})
    readiness = el6.get("disco_readiness") or {}
    if "tftp" not in (readiness.get("xinetd_services") or []):
        errors.append("el6-legacy: tftp missing from xinetd_services")
    if "ntp" not in (readiness.get("deprecated_packages") or []):
        errors.append("el6-legacy: ntp missing from deprecated_packages")

    el9 = (hosts.get("el9-extended", {}).get("disco_packages") or {})
    if not any(p["name"] == "htop" for p in el9.get("third_party") or []):
        errors.append("el9-extended: EPEL htop not reported as third-party")

    authselect = (hosts.get("el9-extended", {}).get("disco_security") or {}).get("authselect")
    if authselect != {"configured": True, "profile": "minimal", "features": ["with-mkhomedir"]}:
        errors.append(f"el9-extended: authselect {authselect!r}, expected minimal with-mkhomedir")

    ubuntu = (hosts.get("ubuntu2404-inventory", {}).get("disco_packages") or {})
    if not any(p["name"] == "disco-localtool" for p in ubuntu.get("third_party") or []):
        errors.append("ubuntu2404-inventory: local package not reported as third-party")
    if "nginx" not in (ubuntu.get("locks") or []):
        errors.append("ubuntu2404-inventory: held nginx missing from locks")
    return errors


def validate(facts_dir):
    facts_dir = Path(facts_dir)
    errors = []
    hosts = {}
    for host in EXPECTED_HOSTS:
        path = facts_dir / f"{host}.json"
        try:
            hosts[host] = json.loads(path.read_text())
        except FileNotFoundError:
            errors.append(f"{host}: facts file not found at {path}")
            continue
        except json.JSONDecodeError as exc:
            errors.append(f"{host}: invalid JSON: {exc}")
            continue
        if not isinstance(hosts[host], dict):
            errors.append(f"{host}: facts root is not an object")
            continue
        errors.extend(check_host(host, hosts[host]))

    errors.extend(check_scenarios(hosts))

    if errors:
        print(f"FAIL: {len(errors)} validation error(s):")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"OK: facts validated for {len(EXPECTED_HOSTS)} hosts")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <facts-dir>")
        sys.exit(1)
    sys.exit(validate(sys.argv[1]))
