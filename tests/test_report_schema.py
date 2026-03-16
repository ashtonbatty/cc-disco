"""Validate report structure, types, and null convention.

These tests ensure the report is machine-parseable: correct types for every
field, no English placeholder strings masquerading as data, and consistent
use of null for missing values.
"""
import re
import pytest


# Placeholder strings that must NEVER appear as values in the report.
# These were used in older template versions and are now replaced with null.
FORBIDDEN_PLACEHOLDERS = [
    "unknown",
    "not collected",
    "not configured",
    "not checked",
    "not registered",
    "not installed",
    "no crontab",
    "not present",
    "N/A",
    "N/A (pre-RHEL 8)",
    "none",  # the word "none" as a string value (not YAML null)
]


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


class TestNullConvention:
    """No English placeholder strings should appear anywhere in the report."""

    def test_full_report_no_placeholders(self, full_report):
        """Full report should not contain any forbidden placeholder strings."""
        for path, value in _walk_values(full_report):
            if isinstance(value, str):
                lower = value.strip().lower()
                for placeholder in FORBIDDEN_PLACEHOLDERS:
                    # Exact match only — don't flag substrings in real data
                    assert lower != placeholder.lower(), (
                        f"Forbidden placeholder '{placeholder}' found at {path}: {value!r}"
                    )

    def test_minimal_report_no_placeholders(self, minimal_report):
        """Minimal report (mostly empty) should use null, not placeholder strings."""
        for path, value in _walk_values(minimal_report):
            if isinstance(value, str):
                lower = value.strip().lower()
                for placeholder in FORBIDDEN_PLACEHOLDERS:
                    assert lower != placeholder.lower(), (
                        f"Forbidden placeholder '{placeholder}' found at {path}: {value!r}"
                    )

    def test_minimal_report_uses_null_for_missing(self, minimal_report):
        """Fields that have no data in minimal fixture should be null, not empty strings."""
        host = minimal_report["testhost.example.com"]

        # Scalar fields that should be null when empty
        null_scalars = [
            ("selinux", "status"),
            ("selinux", "config"),
            ("identity", "sssd_conf"),
            ("identity", "realm_list"),
            ("identity", "krb5_conf"),
            ("identity", "nsswitch_conf"),
            ("security", "sudoers_main"),
            ("security", "sshd_config"),
            ("security", "crypto_policy"),
            ("network", "resolv_conf"),
            ("firewall", "firewalld_zones"),
            ("firewall", "nftables_rules"),
            ("kernel", "loaded_modules"),
            ("kernel", "last_kernel_update"),
            ("kernel", "grub_defaults"),
            ("satellite", "subscription_identity"),
            ("satellite", "subscription_status"),
            ("satellite", "satellite_server"),
            ("satellite", "katello_packages"),
            ("migration", "python_versions"),
            ("migration", "openssl_version"),
            ("migration", "java_active_version"),
            ("migration", "alternatives"),
        ]
        for section, field in null_scalars:
            value = host.get(section, {}).get(field, "MISSING")
            assert value is None, (
                f"{section}.{field} should be null when empty, got {value!r}"
            )


class TestFieldTypes:
    """Every field should have the expected type (list, str, int, null, etc.)."""

    # Fields that must always be lists (even when empty)
    LIST_FIELDS = {
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
    }

    # Top-level keys that must themselves be lists
    TOP_LEVEL_LISTS = {"agents_detected", "common_apps"}

    def _check_list_fields(self, host_data, fixture_name):
        """Verify that list fields are always lists, never strings or null."""
        for section, field in self.LIST_FIELDS:
            value = host_data.get(section, {}).get(field, "MISSING")
            assert value != "MISSING", (
                f"[{fixture_name}] {section}.{field} is missing entirely"
            )
            assert isinstance(value, list), (
                f"[{fixture_name}] {section}.{field} should be a list, "
                f"got {type(value).__name__}: {value!r}"
            )

        for field in self.TOP_LEVEL_LISTS:
            value = host_data.get(field, "MISSING")
            assert value != "MISSING", (
                f"[{fixture_name}] {field} is missing entirely"
            )
            assert isinstance(value, list), (
                f"[{fixture_name}] {field} should be a list, "
                f"got {type(value).__name__}: {value!r}"
            )

    def test_full_report_list_fields(self, full_report):
        host = full_report["testhost.example.com"]
        self._check_list_fields(host, "full")

    def test_minimal_report_list_fields(self, minimal_report):
        host = minimal_report["testhost.example.com"]
        self._check_list_fields(host, "minimal")

    def test_numeric_fields_are_numbers(self, full_report):
        """Numeric fields should be int or float, not strings."""
        host = full_report["testhost.example.com"]
        numeric_checks = [
            (host["system"], "uptime_seconds", int),
            (host["system"], "uptime_days", float),
            (host["cpu"], "physical_count", int),
            (host["cpu"], "cores_per_socket", int),
            (host["cpu"], "total_vcpus", int),
            (host["memory"], "total_mb", int),
            (host["memory"], "swap_mb", int),
            (host["packages"], "total_count", int),
            (host["migration"], "packages_32bit_count", int),
        ]
        for section, field, expected_type in numeric_checks:
            value = section[field]
            assert isinstance(value, (int, float)), (
                f"{field} should be numeric, got {type(value).__name__}: {value!r}"
            )

    def test_boolean_fields_are_bools(self, full_report):
        """Boolean fields should be actual booleans."""
        host = full_report["testhost.example.com"]
        assert isinstance(host["identity"]["krb5_keytab_exists"], bool)

    def test_bonding_interfaces_is_list(self, full_report):
        """Bonding interfaces should be a list, not a string."""
        host = full_report["testhost.example.com"]
        ifaces = host["network"]["bonding"]["interfaces"]
        assert isinstance(ifaces, list), (
            f"bonding.interfaces should be list, got {type(ifaces).__name__}"
        )


class TestRawYAMLNoPlaceholders:
    """Scan the raw YAML text for placeholder patterns that might survive
    YAML parsing (e.g., inside block scalars where they'd be parsed as
    strings rather than caught by the dict-walking tests above)."""

    # Patterns that should never appear as standalone values in the report.
    # These catch block scalar content like "    not collected\n"
    FORBIDDEN_PATTERNS = [
        r"^\s+not collected\s*$",
        r"^\s+not configured\s*$",
        r"^\s+not checked\s*$",
        r"^\s+not present\s*$",
        r"^\s+unknown\s*$",
    ]

    def test_full_report_raw_no_placeholders(self, full_report_yaml):
        for pattern in self.FORBIDDEN_PATTERNS:
            matches = re.findall(pattern, full_report_yaml, re.MULTILINE)
            assert not matches, (
                f"Raw YAML contains forbidden placeholder matching {pattern!r}: {matches}"
            )

    def test_minimal_report_raw_no_placeholders(self, minimal_report_yaml):
        for pattern in self.FORBIDDEN_PATTERNS:
            matches = re.findall(pattern, minimal_report_yaml, re.MULTILINE)
            assert not matches, (
                f"Raw YAML contains forbidden placeholder matching {pattern!r}: {matches}"
            )
