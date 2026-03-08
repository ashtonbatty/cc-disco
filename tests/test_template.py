"""Test that the report template renders valid YAML without errors."""
import yaml
import pytest

from conftest import render_report


class TestTemplateRendersValidYAML:
    """The template must produce parseable YAML for every fixture variant."""

    def test_full_hostvars_renders(self, full_report_yaml):
        """Full hostvars should render without Jinja2 errors."""
        assert len(full_report_yaml) > 0

    def test_full_hostvars_parses_as_yaml(self, full_report):
        """Rendered output from full hostvars must parse as valid YAML."""
        assert full_report is not None
        assert isinstance(full_report, dict)

    def test_minimal_hostvars_renders(self, minimal_report_yaml):
        """Minimal hostvars should render without Jinja2 errors."""
        assert len(minimal_report_yaml) > 0

    def test_minimal_hostvars_parses_as_yaml(self, minimal_report):
        """Rendered output from minimal hostvars must parse as valid YAML."""
        assert minimal_report is not None
        assert isinstance(minimal_report, dict)

    def test_empty_host_list_renders(self, jinja_env):
        """An empty host list should render a valid (empty) report."""
        template = jinja_env.get_template("report.yml.j2")
        context = {
            "ansible_managed": "Ansible managed",
            "hostvars": {},
            "report_hosts": [],
            "groups": {"all": []},
        }
        output = template.render(**context)
        parsed = yaml.safe_load(output)
        # With no hosts, the YAML document should be None or empty
        assert parsed is None or parsed == {}


class TestTemplateHostStructure:
    """Each host in the report should have the expected top-level keys."""

    def test_full_host_has_all_sections(self, full_report):
        """A fully-populated host should contain every report section."""
        host_data = full_report["testhost.example.com"]
        expected_sections = [
            "system", "cpu", "memory", "platform", "network", "firewall",
            "storage", "selinux", "security", "identity", "kernel",
            "services", "packages", "satellite", "agents_detected",
            "common_apps", "directories", "migration",
        ]
        for section in expected_sections:
            assert section in host_data, f"Missing section: {section}"

    def test_minimal_host_has_all_sections(self, minimal_report):
        """A minimal host should still contain every report section."""
        host_data = minimal_report["testhost.example.com"]
        expected_sections = [
            "system", "cpu", "memory", "platform", "network", "firewall",
            "storage", "selinux", "security", "identity", "kernel",
            "services", "packages", "satellite", "agents_detected",
            "common_apps", "directories", "migration",
        ]
        for section in expected_sections:
            assert section in host_data, f"Missing section: {section}"


class TestTemplateFieldValues:
    """Verify specific field values are rendered correctly."""

    def test_full_hostname(self, full_report):
        host = full_report["testhost.example.com"]
        assert host["system"]["hostname"] == "rhel8-web01"

    def test_full_platform_vmware(self, full_report):
        host = full_report["testhost.example.com"]
        assert host["platform"]["detected_platform"] == "vmware"

    def test_full_boot_mode_uefi(self, full_report):
        host = full_report["testhost.example.com"]
        assert host["platform"]["boot_mode"] == "UEFI"

    def test_minimal_boot_mode_bios(self, minimal_report):
        host = minimal_report["testhost.example.com"]
        assert host["platform"]["boot_mode"] == "BIOS"

    def test_full_agents_list(self, full_report):
        host = full_report["testhost.example.com"]
        assert isinstance(host["agents_detected"], list)
        assert "crowdstrike" in host["agents_detected"]

    def test_full_deprecated_packages(self, full_report):
        host = full_report["testhost.example.com"]
        assert isinstance(host["migration"]["deprecated_packages"], list)
        assert "ntp" in host["migration"]["deprecated_packages"]

    def test_full_non_rh_packages(self, full_report):
        host = full_report["testhost.example.com"]
        pkgs = host["packages"]["non_redhat_packages"]
        assert isinstance(pkgs, list)
        assert len(pkgs) == 1
        assert pkgs[0]["name"] == "nginx"

    def test_uptime_calculated(self, full_report):
        host = full_report["testhost.example.com"]
        assert host["system"]["uptime_seconds"] == 864000
        assert host["system"]["uptime_days"] == 10.0
