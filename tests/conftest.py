"""Shared helpers: load task files and render their publishing set_facts.

Publishing set_facts are rendered with Jinja2's NativeEnvironment plus shims for
the Ansible filters and tests they use, so tests see the same native types
(dicts, lists, None) that Ansible stores as facts.
"""
import base64
import importlib.util
import json
import os
import re
from pathlib import Path

import jinja2
import jinja2.nativetypes
import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = REPO_ROOT / "tasks"


def _load_test_plugin(name):
    spec = importlib.util.spec_from_file_location(f"disco_test_plugin_{name}", REPO_ROOT / "test_plugins" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TestModule().tests()


PLAYBOOK_TESTS = _load_test_plugin("disco")


# ---------------------------------------------------------------------------
# Ansible filter / test shims
# ---------------------------------------------------------------------------

def _flags(ignorecase=False, multiline=False):
    flags = 0
    if ignorecase:
        flags |= re.I
    if multiline:
        flags |= re.M
    return flags


def _b64decode(value):
    if not value:
        return ""
    return base64.b64decode(value).decode()


def _bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1", "on")
    return bool(value)


def _regex_replace(value="", pattern="", replacement="", ignorecase=False, multiline=False):
    return re.sub(pattern, replacement, str(value), flags=_flags(ignorecase, multiline))


def _regex_search(value, regex, *args, **kwargs):
    """Ansible regex_search: with backrefs ('\\1'), return those groups of the first match."""
    match = re.search(regex, str(value), flags=_flags(kwargs.get("ignorecase"), kwargs.get("multiline")))
    if not match:
        return None
    if not args:
        return match.group(0)
    return [match.group(int(ref.lstrip("\\"))) for ref in args]


def _search(value, pattern="", ignorecase=False, multiline=False):
    if value is None:
        return False
    return bool(re.search(pattern, str(value), flags=_flags(ignorecase, multiline)))


def _match(value, pattern="", ignorecase=False, multiline=False):
    if value is None:
        return False
    return bool(re.match(pattern, str(value), flags=_flags(ignorecase, multiline)))


def make_env():
    """NativeEnvironment configured like Ansible's templar (chainable undefined)."""
    env = jinja2.nativetypes.NativeEnvironment(undefined=jinja2.ChainableUndefined)
    env.filters.update({
        "b64decode": _b64decode,
        "basename": os.path.basename,
        "bool": _bool,
        "from_json": json.loads,
        "regex_replace": _regex_replace,
        "regex_search": _regex_search,
    })
    env.tests.update({"search": _search, "match": _match, **PLAYBOOK_TESTS})
    return env


ENV = make_env()


def render(value, context):
    """Render a task argument the way Ansible would, recursing into dicts and lists."""
    if isinstance(value, str):
        if "{{" in value or "{%" in value:
            return ENV.from_string(value).render(context)
        return value
    if isinstance(value, dict):
        return {k: render(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, context) for v in value]
    return value


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
    """Evaluate a task's `when:` (string or list of strings) against context."""
    conditions = task.get("when")
    if conditions is None:
        return True
    if not isinstance(conditions, list):
        conditions = [conditions]
    for cond in conditions:
        if isinstance(cond, bool):
            result = cond
        else:
            result = ENV.from_string("{{ " + str(cond) + " }}").render(context)
        if not _bool(result):
            return False
    return True


def publish(task_file, context):
    """Run every set_fact in task_file whose `when` holds; return the published facts."""
    facts = {}
    for task in load_tasks(task_file):
        args = task.get("ansible.builtin.set_fact")
        if args is None or not when_holds(task, context):
            continue
        ctx = dict(context)
        for name, value in (task.get("vars") or {}).items():
            ctx[name] = render(value, ctx)
        for key, value in args.items():
            if key != "cacheable":
                facts[key] = render(value, ctx)
    return facts


def controls_vars(facts, extra=None):
    """Render vars/controls.yml for a host with the given setup facts."""
    raw = yaml.safe_load((REPO_ROOT / "vars" / "controls.yml").read_text())
    context = {"ansible_facts": facts, **(extra or {})}
    resolved = {}
    # Values reference each other; render in passes until stable.
    for _ in range(5):
        for name, value in raw.items():
            if name in (extra or {}):
                continue
            resolved[name] = render(value, {**context, **resolved})
    return {**resolved, **(extra or {})}


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


def slurp(content=""):
    return {"content": base64.b64encode(content.encode()).decode() if content else "", "encoding": "base64"}


def slurp_missing():
    return {"failed": False, "msg": "file not found: /etc/missing"}


def find(paths=None):
    paths = paths or []
    return {"files": [{"path": p} for p in paths], "matched": len(paths)}


def stat(exists=True):
    return {"stat": {"exists": exists}}


def uri(status=200):
    return {"status": status}


def loop_results(items):
    """Build a slurp-with-loop result: items is a list of (item, content-or-None)."""
    results = []
    for item, content in items:
        entry = {"item": item}
        if content is not None:
            entry.update(slurp(content), source=item["path"] if isinstance(item, dict) else item)
        results.append(entry)
    return {"results": results}


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
