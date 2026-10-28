# CLAUDE.md — cc-disco

## What This Is

Read-only Ansible discovery for Linux (RHEL 6–10, Ubuntu) and Windows Server. Everything discovered is published as cacheable facts. An **inventory** layer (packages, services, processes, ports, component versions, containers) runs on every host, for vulnerability response. A **migration** layer runs only on RHEL-family 6/7/8, for RHEL 9/10 upgrade planning. Nothing is modified on target hosts.

## Key Conventions

### Facts, not reports
- Each `tasks/**/<section>.yml` collects raw probe output into registers, then publishes **one** fact, `disco_<section>`, with `set_fact` and `cacheable: true`. There are no report templates.
- **Mirror facts:** where a standard fact module defines the shape, publish under its name instead, so one query works on every OS. These are `packages` (package_facts), `services` (service_facts), and `tcp_listen` / `udp_listen` (listen_ports_facts).
- **Single expression:** write each published value as one Jinja expression (or `{% set %}` statements ending in a single `{{ value }}`) that yields the whole dict or list. That keeps types and `null`s intact on ansible-core 2.11–2.18 (non-native templating) and on 2.19+.
- **Literal null:** a fact whose *entire* value may be `null` needs a separate "… as unavailable" task that sets a literal YAML `null`. A templated `none` renders as `""` before 2.19.
- **Null convention:** `null` means not collected (skipped, missing source, or failed command), and `[]` means collected and empty. Never use placeholder strings.
- **Untrusted content:** later tasks read *registers*, never published facts. Probe output can contain `{{ … }}`, and published facts aren't marked unsafe in every core version.
- **Don't duplicate setup:** check `ansible -m setup`, `package_facts` and `service_facts` before adding a probe.

### Variable Naming
All registered variables, and all published facts except the mirror facts, use the `disco_` prefix. Never break this convention.

### Read-Only Contract
- Every task must be read-only. Use `changed_when: false` on all command/shell/win_* probe tasks.
- Never use modules that modify state (e.g. `copy`, `template`, `service`, `win_regedit`) on targets.
- `win_powershell` scripts start with `$Ansible.Changed = $false`.
- yum/dnf only run through `{{ disco_yum }}` (cache-only `-C`, subscription-manager/product-id plugins disabled), so metadata isn't refreshed and `redhat.repo` isn't rewritten.

### Compatibility
- Linux task files use `ansible.builtin` only, and their syntax must work on ansible-core 2.11 (RHEL 6).
- Windows task files (`tasks/windows/`) use `ansible.windows`. They are reached only via `include_tasks` in the Windows play, so controllers without that collection can still parse the playbook.

### Tag System
Each task file uses a single primary tag matching its filename (e.g. `tasks/migration/network.yml` uses `[network]`). Linux and Windows files with the same name share a tag. A task whose output is consumed by another section also carries that section's tag (see the Tags table in README.md).

## Running Tests

```bash
ansible-lint                                 # Lint all playbooks and tasks
pytest tests/ --ignore=tests/integration     # Conventions + publish-fact rendering
make -C tests/integration test-integration   # Container targets, core 2.11 + 2.16
```

`tests/test_task_conventions.py` enforces the conventions above. `tests/test_published_facts.py` renders every publish task against fixtures.

## Project Structure

```
gather_facts.yml          # Plays: reset cache → Linux discovery → Windows discovery → export
vars/controls.yml         # Profile selection, knobs, package-manager helpers (shared by both plays)
tasks/controls.yml        # Publishes disco_controls
tasks/linux/              # Inventory layer, every Linux host
tasks/migration/          # Migration layer, RHEL-family 6/7/8 only
tasks/windows/            # Inventory layer, Windows (included dynamically)
tests/                    # Unit + integration tests
inventory/                # Inventory files
```
