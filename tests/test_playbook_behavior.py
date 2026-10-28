"""Regression tests for playbook task selection and task-source semantics."""
import os
import subprocess

from conftest import REPO_ROOT, load_task

EXPORT_TASK = "Write per-host facts file"
RESET_TASK = "Clear cached facts"
CONTROLS_TASK = "Publish discovery controls"


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


class TestTaggedPlaybookBehavior:
    """Tagged runs pull in their producers, the controls, the reset and the export."""

    def test_every_tagged_run_resets_publishes_controls_and_exports(self):
        output = _list_tasks("network")
        for task in (RESET_TASK, CONTROLS_TASK, EXPORT_TASK, "Publish network facts"):
            assert task in output
        assert "Publish package facts" not in output

    def test_readiness_tag_includes_producers(self):
        output = _list_tasks("readiness")
        assert "Collect installed package facts" in output
        assert "Probe fstab, xinetd, alternatives and cron" in output
        assert "Publish migration readiness facts" in output

    def test_apps_and_satellite_tags_include_package_facts(self):
        for tag in ("apps", "satellite"):
            assert "Collect installed package facts" in _list_tasks(tag)

    def test_firewall_tag_includes_service_facts(self):
        assert "Collect service facts" in _list_tasks("firewall")

    def test_ports_tag_includes_process_list(self):
        output = _list_tasks("ports")
        assert "List running processes" in output
        assert "Publish listening port facts" in output

    def test_deep_tags_still_publish(self):
        assert "Publish kernel facts" in _list_tasks("deep_kernel")
        assert "Publish security facts" in _list_tasks("deep_security")
        assert "Publish filesystem facts" in _list_tasks("deep_filesystem")

    def test_windows_play_is_listed(self):
        output = _list_tasks()
        assert "Windows discovery" in output
        assert "Include Windows package tasks" in output


class TestTaskSemantics:
    """Task-source regression tests for shell expressions."""

    def test_backup_task_uses_real_newline_output(self):
        task = load_task("tasks/extended/backup.yml", "Detect backup and monitoring agents")
        shell = task["ansible.builtin.shell"]
        assert "printf '%s\\n'" in shell
        assert 'found="${found}' not in shell
        assert '\\n"' not in shell
