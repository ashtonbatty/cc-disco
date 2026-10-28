"""Jinja test `disco_collected`: did a registered probe run and return its data?

The null convention (null = not collected) needs one answer to that question
for every kind of probe. Publish tasks write `reg is disco_collected` instead of
module-specific checks:

- skipped, or never run (undefined, e.g. outside the selected --tags): no
- command / shell / win_command (has rc): only rc 0
- any other module: its data key is present (stat stat, uri status,
  win_powershell output, win_service_info services, win_feature_info
  features). With failed_when: false a failed module leaves only `msg` behind.
- batched migration probes: each entry from the disco_probes filter has an rc.

Probes whose non-zero rc still carries data (e.g. `subscription-manager status`
when unregistered) don't use this test.
"""
from collections.abc import Mapping

try:
    from ansible.template import accept_args_markers
except ImportError:  # ansible-core < 2.19 passes Undefined to tests as-is
    def accept_args_markers(func):
        return func

DATA_KEYS = ("stat", "status", "output", "services", "features")


@accept_args_markers
def collected(result):
    if not isinstance(result, Mapping) or result.get("skipped"):
        return False
    if "rc" in result:
        return result["rc"] == 0
    return any(key in result for key in DATA_KEYS)


class TestModule:
    def tests(self):
        return {"disco_collected": collected}
