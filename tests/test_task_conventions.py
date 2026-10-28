"""Static checks over tasks/ that enforce the project's conventions.

- Read-only contract: probes never report changes and no state-changing module is used.
- Registered variables use the disco_ prefix.
- Every task file publishes cacheable facts named disco_<file>, or a mirror name
  that matches a standard fact module (packages, services, tcp_listen, udp_listen).
- Windows tasks are only reached through include_tasks, and Linux tasks only use
  ansible.builtin, so a controller without ansible.windows can parse the playbook.
- yum/dnf always run cache-only with the subscription plugins disabled.
"""
import re

import pytest
import yaml

from conftest import REPO_ROOT, TASKS_DIR, load_tasks


TASK_FILES = sorted(p.relative_to(REPO_ROOT).as_posix() for p in TASKS_DIR.rglob("*.yml"))
SECTION_FILES = [f for f in TASK_FILES if f != "tasks/controls.yml"]

PROBE_MODULES = {
    "ansible.builtin.command", "ansible.builtin.shell", "ansible.builtin.raw",
    "ansible.windows.win_command", "ansible.windows.win_shell", "ansible.windows.win_powershell",
}
STATE_CHANGING_MODULES = {
    "copy", "template", "file", "lineinfile", "blockinfile", "replace", "service", "systemd",
    "systemd_service", "package", "yum", "dnf", "apt", "user", "group", "cron", "mount",
    "get_url", "unarchive", "git", "reboot", "sysvinit", "assemble", "script",
    "win_copy", "win_file", "win_template", "win_service", "win_package", "win_feature",
    "win_updates", "win_regedit", "win_reboot", "win_hotfix", "win_optional_feature",
}
# Fact modules whose output already is a fact (no set_fact needed).
FACT_MODULES = {
    "ansible.builtin.package_facts", "ansible.builtin.service_facts",
    "ansible.windows.win_listen_ports_facts",
}
# Facts that deliberately mirror a standard module's name and shape.
MIRROR_FACTS = {"packages", "services", "tcp_listen", "udp_listen"}
SENSITIVE_SECTIONS = {"tasks/migration/security.yml", "tasks/migration/identity.yml"}


def _module(task):
    for key in task:
        if "." in key and key.split(".")[0] in ("ansible", "community"):
            return key
    return None


def _all_tasks():
    for task_file in TASK_FILES:
        for task in load_tasks(task_file):
            yield task_file, task


@pytest.mark.parametrize("task_file", TASK_FILES)
def test_every_task_is_named_and_fqcn(task_file):
    for task in load_tasks(task_file):
        assert task.get("name"), f"{task_file}: unnamed task {task}"
        assert _module(task), f"{task_file}: {task['name']!r} has no FQCN module"


@pytest.mark.parametrize("task_file", TASK_FILES)
def test_probes_never_report_changes(task_file):
    for task in load_tasks(task_file):
        if _module(task) in PROBE_MODULES:
            assert task.get("changed_when") is False, f"{task_file}: {task['name']!r} needs changed_when: false"


@pytest.mark.parametrize("task_file", TASK_FILES)
def test_no_state_changing_modules(task_file):
    for task in load_tasks(task_file):
        leaf = _module(task).split(".")[-1]
        assert leaf not in STATE_CHANGING_MODULES, f"{task_file}: {task['name']!r} uses {leaf}"


@pytest.mark.parametrize("task_file", TASK_FILES)
def test_registers_use_disco_prefix(task_file):
    for task in load_tasks(task_file):
        if "register" in task:
            assert task["register"].startswith("disco_"), f"{task_file}: register {task['register']!r}"


@pytest.mark.parametrize("task_file", TASK_FILES)
def test_set_facts_are_cacheable(task_file):
    """Everything discovered must reach ansible_facts (and so the fact cache / export)."""
    for task in load_tasks(task_file):
        args = task.get("ansible.builtin.set_fact")
        if args is not None:
            assert args.get("cacheable") is True, f"{task_file}: {task['name']!r} is not cacheable"


@pytest.mark.parametrize("task_file", SECTION_FILES)
def test_section_publishes_its_own_fact(task_file):
    stem = task_file.rsplit("/", 1)[-1].removesuffix(".yml")
    allowed = {f"disco_{stem}"} | MIRROR_FACTS
    published = set()
    uses_fact_module = False
    for task in load_tasks(task_file):
        args = task.get("ansible.builtin.set_fact")
        if args is not None:
            published |= set(args) - {"cacheable"}
        if _module(task) in FACT_MODULES:
            uses_fact_module = True
    assert published <= allowed, f"{task_file} publishes {published - allowed}, expected disco_{stem} or a mirror"
    assert published or uses_fact_module, f"{task_file} publishes nothing"


@pytest.mark.parametrize("task_file", sorted(SENSITIVE_SECTIONS))
def test_sensitive_publishes_are_no_log(task_file):
    for task in load_tasks(task_file):
        if "ansible.builtin.set_fact" in task:
            assert task.get("no_log") is True, f"{task_file}: {task['name']!r} must be no_log"


@pytest.mark.parametrize("task_file", [f for f in TASK_FILES if not f.startswith("tasks/windows/")])
def test_linux_tasks_use_builtin_only(task_file):
    for task in load_tasks(task_file):
        assert _module(task).startswith("ansible.builtin."), f"{task_file}: {task['name']!r}"


@pytest.mark.parametrize("task_file", [f for f in TASK_FILES if f.startswith("tasks/windows/")])
def test_win_powershell_scripts_report_unchanged(task_file):
    for task in load_tasks(task_file):
        args = task.get("ansible.windows.win_powershell")
        if args is not None:
            assert "$Ansible.Changed = $false" in args["script"], f"{task_file}: {task['name']!r}"


def test_windows_tasks_only_included_dynamically():
    plays = yaml.safe_load((REPO_ROOT / "gather_facts.yml").read_text())
    for play in plays:
        for task in play.get("tasks", []):
            imported = task.get("ansible.builtin.import_tasks", "")
            assert not str(imported).startswith("tasks/windows/"), f"static import of {imported}"
    windows_play = next(p for p in plays if p["hosts"] == "windows")
    included = {t["ansible.builtin.include_tasks"] for t in windows_play["tasks"] if "ansible.builtin.include_tasks" in t}
    on_disk = {f for f in TASK_FILES if f.startswith("tasks/windows/")}
    assert included == on_disk


def test_discovery_plays_use_free_strategy():
    """Discovery tasks never read another host's data, so no host waits for the slowest."""
    plays = yaml.safe_load((REPO_ROOT / "gather_facts.yml").read_text())
    for play in plays:
        if play["name"].endswith(" discovery"):
            assert play.get("strategy") == "free", play["name"]
    for task_file, task in _all_tasks():
        text = yaml.safe_dump(task)
        for marker in ("run_once", "delegate_to", "hostvars"):
            assert marker not in text, f"{task_file}: {task['name']!r} uses {marker} under strategy: free"


def test_linux_setup_skips_facter_and_ohai():
    plays = yaml.safe_load((REPO_ROOT / "gather_facts.yml").read_text())
    linux_play = next(p for p in plays if p["hosts"] == "all:!windows")
    assert {"all", "!facter", "!ohai"} <= set(linux_play["gather_subset"])


def test_every_linux_task_file_is_imported():
    plays = yaml.safe_load((REPO_ROOT / "gather_facts.yml").read_text())
    linux_play = next(p for p in plays if p["hosts"] == "all:!windows")
    imported = set()
    for task in linux_play["tasks"]:
        for inner in [task] + task.get("block", []):
            if "ansible.builtin.import_tasks" in inner:
                imported.add(inner["ansible.builtin.import_tasks"])
    expected = {f for f in TASK_FILES if not f.startswith("tasks/windows/")}
    assert imported == expected


@pytest.mark.parametrize("task_file", TASK_FILES)
def test_collected_checks_use_disco_collected(task_file):
    """One answer to "was this probe collected?": the disco_collected test plugin.

    Ad-hoc forms drift apart (rc is defined vs rc == 0, files is defined, ...)
    and then publish [] for a probe that failed.
    """
    adhoc = re.compile(r"\.rc\b|(?<!ansible_facts)\.\w+ is (not )?defined")
    text = (REPO_ROOT / task_file).read_text()
    assert not adhoc.search(text), f"{task_file}: use `<register> is disco_collected`"


def test_yum_and_dnf_only_run_through_disco_yum():
    pattern = re.compile(r"(^|[\s;&|(])(yum|dnf)\s")
    for task_file, task in _all_tasks():
        module = _module(task)
        if module not in PROBE_MODULES:
            continue
        args = task[module]
        text = args if isinstance(args, str) else " ".join(str(v) for v in (args.get("argv") or [args.get("cmd", "")]))
        assert not pattern.search(text), f"{task_file}: {task['name']!r} calls yum/dnf directly"

    controls = yaml.safe_load((REPO_ROOT / "vars" / "controls.yml").read_text())
    assert "-C" in controls["disco_yum"]
    assert "--disableplugin=subscription-manager,product-id" in controls["disco_yum"]
