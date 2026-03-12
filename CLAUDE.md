# CLAUDE.md — cc-disco

## What This Is

Ansible playbook for read-only RHEL 6/7/8 server discovery and audit, targeting migration planning to RHEL 9/10. Nothing is modified on target hosts.

## Key Conventions

### Variable Naming
All registered variables use the `disco_` prefix (e.g., `disco_routes`, `disco_sshd_config`). Never break this convention.

### Read-Only Contract
Every task must be read-only. Use `changed_when: false` on all command/shell tasks. Never use modules that modify state (e.g., `copy`, `template`, `service` on targets).

### Tag System
Each task file uses a single primary tag matching its filename (e.g., `tasks/network.yml` uses `[network]`). Some tasks carry additional tags when their output is consumed by other sections — see the Tag Dependencies table in README.md.

### Task / Template 1:1 Mapping
Each `tasks/<section>.yml` has a corresponding `templates/sections/<section>.j2`. Keep them in sync — variables registered in a task file are rendered in its matching template.

## Running Tests

```bash
ansible-lint                  # Lint all playbooks and tasks
pytest tests/                 # Schema validation and template tests
```

## Project Structure

```
gather_facts.yml              # Main playbook entrypoint
tasks/                        # Per-section task includes
templates/sections/           # Per-section Jinja2 report fragments
templates/report.yml.j2       # Top-level report template
tests/                        # Integration and unit tests
inventory/                    # Inventory files
```
