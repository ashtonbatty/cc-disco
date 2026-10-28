"""Shared helpers: load task files and render their publishing set_facts.

Publishing set_facts are rendered by ansible-core's own templating engine, with
the playbook's test_plugins loaded, so tests see the real filters, tests, native
types and None handling of the installed core (2.19+). The integration suite
covers the older cores' non-native templating.
"""
import base64
from pathlib import Path

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.plugins.loader import filter_loader, init_plugin_loader, test_loader
from ansible.template import Templar

try:
    from ansible.template import trust_as_template
except ImportError as exc:  # pragma: no cover
    raise ImportError("the unit tests render with ansible-core's templating and need ansible-core 2.19+") from exc


REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = REPO_ROOT / "tasks"

init_plugin_loader()
test_loader.add_directory(str(REPO_ROOT / "test_plugins"))
filter_loader.add_directory(str(REPO_ROOT / "filter_plugins"))
LOADER = DataLoader()


def _templar(context):
    return Templar(loader=LOADER, variables=context)


def load_trusted(path):
    """Load a playbook file the way Ansible does: its strings are trusted templates."""
    return LOADER.load_from_file(str(REPO_ROOT / path), trusted_as_template=True) or []


def render(value, context):
    """Template a value (str, dict or list) loaded from a playbook file."""
    return _templar(context).template(value)


def evaluate(expression, context):
    """Evaluate a bare expression, as in a when: (literal test expressions are trusted)."""
    if isinstance(expression, bool):
        return expression
    return _templar(context).evaluate_conditional(trust_as_template(expression))


# ---------------------------------------------------------------------------
# Task file access
# ---------------------------------------------------------------------------

def load_tasks(task_file):
    return yaml.safe_load((REPO_ROOT / task_file).read_text()) or []


def load_task(task_file, task_name):
    for task in load_tasks(task_file):
        if task.get("name") == task_name:
            return task
    raise AssertionError(f"Task {task_name!r} not found in {task_file}")


def when_holds(task, context):
    """Evaluate a task's `when:` (one condition or a list) against context."""
    conditions = task.get("when")
    if conditions is None:
        return True
    if not isinstance(conditions, list):
        conditions = [conditions]
    return all(evaluate(cond, context) for cond in conditions)


def publish(task_file, context):
    """Run every set_fact in task_file whose `when` holds; return the published facts."""
    facts = {}
    for task in load_trusted(task_file):
        args = task.get("ansible.builtin.set_fact")
        if args is None or not when_holds(task, context):
            continue
        ctx = {**context, **(task.get("vars") or {})}
        facts.update(render({k: v for k, v in args.items() if k != "cacheable"}, ctx))
    return facts


def controls_vars(facts, extra=None):
    """vars/controls.yml rendered for a host with the given setup facts (and extra vars)."""
    variables = {**load_trusted("vars/controls.yml"), "ansible_facts": facts, **(extra or {})}
    templar = _templar(variables)
    return {name: templar.template(value) for name, value in variables.items() if name != "ansible_facts"}


# ---------------------------------------------------------------------------
# Builders for Ansible-shaped registered results
# ---------------------------------------------------------------------------

def cmd(stdout="", rc=0, stderr=""):
    return {
        "stdout": stdout,
        "stdout_lines": stdout.splitlines(),
        "stderr": stderr,
        "stderr_lines": stderr.splitlines(),
        "rc": rc,
        "changed": False,
    }


def missing_cmd():
    """A command whose binary is absent (command module rc 2, no stdout)."""
    return {"rc": 2, "msg": "[Errno 2] No such file or directory", "changed": False, "stdout": "", "stdout_lines": []}


def skipped():
    return {"changed": False, "skipped": True, "skip_reason": "Conditional result was False"}


def stat(exists=True):
    return {"stat": {"exists": exists}}


def uri(status=200):
    return {"status": status}


def probes(entries):
    """A batched probe task's register: entries maps name -> output, or (rc, output).

    Mirrors disco_probe_sh in vars/controls.yml: one name|rc|base64(output) line each.
    """
    lines = []
    for name, value in entries.items():
        rc, out = value if isinstance(value, tuple) else (0, value)
        lines.append(f"{name}|{rc}|{base64.b64encode(out.encode()).decode()}")
    return cmd("\n".join(lines))


# ---------------------------------------------------------------------------
# Null-convention helpers
# ---------------------------------------------------------------------------

# English placeholders that older versions emitted instead of null.
FORBIDDEN_PLACEHOLDERS = {
    "unknown", "not collected", "not configured", "not checked", "not registered",
    "not installed", "no crontab", "not present", "n/a", "none", "not found",
}


def walk(obj, path=""):
    """Yield (path, value) for every leaf in nested dicts/lists."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            yield from walk(val, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            yield from walk(val, f"{path}[{i}]")
    else:
        yield path, obj


def assert_no_placeholders(obj):
    for path, value in walk(obj):
        if isinstance(value, str):
            assert value.strip().lower() not in FORBIDDEN_PLACEHOLDERS, f"placeholder {value!r} at {path}"
            assert value != "", f"empty string at {path} (use null)"


@pytest.fixture
def rhel8_facts():
    return {
        "distribution": "RedHat",
        "distribution_major_version": "8",
        "pkg_mgr": "dnf",
        "system_vendor": "VMware, Inc.",
        "virtualization_role": "guest",
        "virtualization_type": "VMware",
        "date_time": {"iso8601": "2026-10-28T12:00:00Z"},
        "packages": {
            "bash": [{"name": "bash", "version": "4.4.20", "release": "4.el8", "arch": "x86_64"}],
            "glibc": [
                {"name": "glibc", "version": "2.28", "release": "225.el8", "arch": "x86_64"},
                {"name": "glibc", "version": "2.28", "release": "225.el8", "arch": "i686"},
            ],
            "ntp": [{"name": "ntp", "version": "4.2.8", "release": "1.el8", "arch": "x86_64"}],
            "nginx": [{"name": "nginx", "version": "1.20.1", "release": "1.el8", "arch": "x86_64"}],
            "java-1.8.0-openjdk": [{"name": "java-1.8.0-openjdk", "version": "1.8.0.362", "release": "4.el8", "arch": "x86_64"}],
            "katello-host-tools": [{"name": "katello-host-tools", "version": "4.0.0", "release": "1.el8", "arch": "noarch"}],
        },
        "services": {
            "firewalld.service": {"name": "firewalld.service", "state": "running", "status": "enabled", "source": "systemd"},
        },
    }


@pytest.fixture
def ubuntu_facts():
    return {
        "distribution": "Ubuntu",
        "distribution_major_version": "24",
        "pkg_mgr": "apt",
        "date_time": {"iso8601": "2026-10-28T12:00:00Z"},
        "packages": {
            "openssl": [{"name": "openssl", "version": "3.0.13-0ubuntu3.4", "arch": "amd64", "origin": "Ubuntu"}],
            "docker-ce": [{"name": "docker-ce", "version": "5:27.3.1-1~ubuntu.24.04~noble", "arch": "amd64", "origin": "Docker"}],
            "localtool": [{"name": "localtool", "version": "1.0", "arch": "amd64", "origin": ""}],
        },
    }
