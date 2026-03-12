"""Regression tests for playbook task selection and task-source semantics."""
from pathlib import Path
import os
import subprocess

import jinja2
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def _ansible_env():
    env = os.environ.copy()
    env["ANSIBLE_LOCAL_TEMP"] = "/tmp/ansible-local"
    env["ANSIBLE_REMOTE_TEMP"] = "/tmp/ansible-remote"
    env["ANSIBLE_HOME"] = "/tmp/ansible-home"
    return env


def _list_tasks(*tags):
    cmd = ["ansible-playbook", "gather_facts.yml", "--list-tasks"]
    if tags:
        cmd.extend(["--tags", ",".join(tags)])
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        check=True,
        env=_ansible_env(),
        capture_output=True,
        text=True,
    ).stdout


def _load_task(task_file, task_name):
    tasks = yaml.safe_load((REPO_ROOT / task_file).read_text())
    for task in tasks:
        if task.get("name") == task_name:
            return task
    raise AssertionError(f"Task {task_name!r} not found in {task_file}")


class TestTaggedPlaybookBehavior:
    """Tagged runs should include required prerequisites and report generation."""

    def test_readiness_tag_includes_prereqs_and_report(self):
        output = _list_tasks("readiness")
        assert "Collect package facts for structured package analysis" in output
        assert "Collect service facts for structured service analysis" in output
        assert "Render consolidated discovery report" in output

    def test_apps_tag_includes_package_facts_and_report(self):
        output = _list_tasks("apps")
        assert "Collect package facts for structured package analysis" in output
        assert "Build common server application list from package facts" in output
        assert "Render consolidated discovery report" in output


class TestReadinessTaskSemantics:
    """Task-source regression tests for shell and Jinja expressions."""

    def test_backup_task_uses_real_newline_output(self):
        task = _load_task("tasks/backup.yml", "Detect backup and monitoring agents")
        shell = task["ansible.builtin.shell"]
        assert "printf '%s\\n'" in shell
        assert 'found="${found}' not in shell
        assert '\\n"' not in shell

    def test_time_service_template_supports_bare_service_names(self):
        task = _load_task(
            "tasks/readiness.yml",
            "Build chronyd vs ntpd status from service facts",
        )
        template = jinja2.Environment().from_string(
            task["ansible.builtin.set_fact"]["disco_time_services"]
        )
        rendered = template.render(
            ansible_facts={
                "services": {
                    "ntpd": {"state": "running"},
                    "chronyd": {"state": "stopped"},
                }
            }
        )
        lines = rendered.strip().splitlines()
        assert lines == ["ntpd:running", "chronyd:stopped"]
