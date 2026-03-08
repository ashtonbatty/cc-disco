#!/usr/bin/env python3
"""Validate the integration test discovery report.

Checks:
1. Report file exists and parses as valid YAML
2. All 3 target hosts appear as top-level keys
3. All 18 sections present per host
4. No forbidden placeholder strings (in template-controlled fields only)
5. Scenario-specific assertions
"""
import sys

import yaml


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_HOSTS = ["el7-webserver", "el7-minimal", "el6-legacy"]

EXPECTED_SECTIONS = [
    "system", "cpu", "memory", "platform", "network", "firewall",
    "storage", "selinux", "security", "identity", "kernel", "services",
    "packages", "satellite", "agents_detected", "common_apps",
    "directories", "migration",
]

# Placeholder strings that should never appear as template-controlled values.
# NOTE: "unknown" and "none" are excluded here because they can appear as
# legitimate RPM metadata (e.g., vendor: "unknown") or command output.
FORBIDDEN_PLACEHOLDERS = [
    "not collected",
    "not configured",
    "not checked",
    "not registered",
    "not installed",
    "no crontab",
    "not present",
    "N/A",
    "N/A (pre-RHEL 8)",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def walk_values(obj, path=""):
    """Yield (path, value) for every leaf value in a nested dict/list."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            yield from walk_values(val, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            yield from walk_values(val, f"{path}[{i}]")
    else:
        yield path, obj


def check_no_placeholders(host_data, hostname):
    """Ensure no forbidden placeholder strings appear in the report."""
    errors = []
    for path, value in walk_values(host_data):
        if isinstance(value, str):
            lower = value.strip().lower()
            for placeholder in FORBIDDEN_PLACEHOLDERS:
                if lower == placeholder.lower():
                    errors.append(
                        f"  {hostname}{path}: forbidden placeholder '{placeholder}' "
                        f"(got {value!r})"
                    )
    return errors


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------

def validate(report_path):
    errors = []

    # 1. Parse YAML
    try:
        with open(report_path) as f:
            report = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"FAIL: Report file not found: {report_path}")
        return 1
    except yaml.YAMLError as e:
        print(f"FAIL: Report is not valid YAML: {e}")
        return 1

    if not isinstance(report, dict):
        print(f"FAIL: Report root is not a dict (got {type(report).__name__})")
        return 1

    # 2. Check all hosts present
    for host in EXPECTED_HOSTS:
        if host not in report:
            errors.append(f"Missing host: {host}")

    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        return 1

    # 3. Check all sections present per host
    for host in EXPECTED_HOSTS:
        host_data = report[host]
        if not isinstance(host_data, dict):
            errors.append(f"{host}: host data is not a dict")
            continue
        for section in EXPECTED_SECTIONS:
            if section not in host_data:
                errors.append(f"{host}: missing section '{section}'")

    # 4. Check no placeholder strings
    for host in EXPECTED_HOSTS:
        host_data = report[host]
        if isinstance(host_data, dict):
            errors.extend(check_no_placeholders(host_data, host))

    # 5. Scenario-specific assertions
    errors.extend(validate_el7_webserver(report.get("el7-webserver", {})))
    errors.extend(validate_el7_minimal(report.get("el7-minimal", {})))
    errors.extend(validate_el6_legacy(report.get("el6-legacy", {})))

    if errors:
        print(f"FAIL: {len(errors)} validation error(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"OK: Report validated — {len(EXPECTED_HOSTS)} hosts, "
          f"{len(EXPECTED_SECTIONS)} sections each")
    return 0


def validate_el7_webserver(host):
    """el7-webserver: agents and common_apps present."""
    errors = []
    if not isinstance(host, dict):
        return ["el7-webserver: host data is not a dict"]

    # agents_detected should include crowdstrike and splunk (from /opt dirs)
    agents = host.get("agents_detected", [])
    if isinstance(agents, list):
        agents_lower = [a.lower() if isinstance(a, str) else str(a).lower()
                        for a in agents]
        for expected in ["crowdstrike", "splunk"]:
            if not any(expected in a for a in agents_lower):
                errors.append(
                    f"el7-webserver: agents_detected should include "
                    f"'{expected}', got {agents}"
                )

    # common_apps should include httpd (nginx may not be detected depending
    # on the detection method — package_facts vs binary check)
    apps = host.get("common_apps", [])
    if isinstance(apps, list):
        apps_lower = [a.lower() if isinstance(a, str) else str(a).lower()
                      for a in apps]
        if not any("httpd" in a for a in apps_lower):
            errors.append(
                f"el7-webserver: common_apps should include "
                f"'httpd', got {apps}"
            )

    return errors


def validate_el7_minimal(host):
    """el7-minimal: no agents."""
    errors = []
    if not isinstance(host, dict):
        return ["el7-minimal: host data is not a dict"]

    # agents_detected should be empty
    agents = host.get("agents_detected", [])
    if isinstance(agents, list) and len(agents) > 0:
        errors.append(
            f"el7-minimal: agents_detected should be empty, got {agents}"
        )

    return errors


def validate_el6_legacy(host):
    """el6-legacy: xinetd services non-empty, deprecated packages include ntp."""
    errors = []
    if not isinstance(host, dict):
        return ["el6-legacy: host data is not a dict"]

    migration = host.get("migration", {})
    if isinstance(migration, dict):
        # xinetd_services should be non-empty
        xinetd = migration.get("xinetd_services", [])
        if isinstance(xinetd, list) and len(xinetd) == 0:
            errors.append(
                "el6-legacy: migration.xinetd_services should be non-empty"
            )

        # deprecated_packages should include ntp
        deprecated = migration.get("deprecated_packages", [])
        if isinstance(deprecated, list):
            dep_lower = [str(d).lower() for d in deprecated]
            if "ntp" not in dep_lower:
                errors.append(
                    f"el6-legacy: migration.deprecated_packages should include "
                    f"'ntp', got {deprecated}"
                )

    return errors


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <report.yml>")
        sys.exit(1)
    sys.exit(validate(sys.argv[1]))
