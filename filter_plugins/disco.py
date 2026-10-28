"""Jinja filter `disco_probes`: unpack a batched probe task's output.

Migration sections run all their commands in one shell task (one round trip
instead of one per command). The disco_probe_sh helpers (vars/controls.yml)
print one line per command, name|rc|base64(output), so output can't break the
framing. This filter turns those lines back into {name: {rc, stdout,
stdout_lines}}, the shape of a command register, so every field still gates on
`p.<name> is disco_collected`. A command that didn't run (knob off, task
skipped or never run) has no entry.
"""
import base64
import binascii
from collections.abc import Mapping

try:
    from ansible.template import accept_args_markers

    def _untrusted(value):  # 2.19+: plain strings are never trusted as templates
        return value
except ImportError:  # ansible-core < 2.19: mark probe output unsafe, as registers are
    from ansible.utils.unsafe_proxy import wrap_var as _untrusted

    def accept_args_markers(func):
        return func


@accept_args_markers
def probes(result):
    entries = {}
    if not isinstance(result, Mapping) or result.get("skipped"):
        return entries
    for line in result.get("stdout_lines") or []:
        fields = str(line).rsplit("|", 2)
        if len(fields) != 3 or not fields[1].isdigit():
            continue
        name, rc, encoded = fields
        try:
            stdout = base64.b64decode(encoded).decode("utf-8", "replace")
        except (binascii.Error, ValueError):
            continue
        entries[name] = {"rc": int(rc), "stdout": stdout, "stdout_lines": stdout.splitlines()}
    return _untrusted(entries)


class FilterModule:
    def filters(self):
        return {"disco_probes": probes}
