"""Private, whole-source reversible dispatch for immutable independent readers.

Only literal version/import dispatch changes are permitted. Native input files
are never rewritten. The original source hash and exact inverse are reported.
"""

import hashlib
from pathlib import Path
from types import ModuleType
import uuid


def project_module(filename, expected_sha256, replacements):
    path = Path(__file__).with_name(filename)
    original = path.read_bytes()
    digest = lambda raw: hashlib.sha256(raw).hexdigest()
    if digest(original) != expected_sha256:
        raise ValueError("immutable reader source differs: " + filename)
    payload, changes = original, []
    for before, after, count in replacements:
        before, after = before.encode(), after.encode()
        if before == after or payload.count(before) != count or after in payload:
            raise ValueError("literal reader projection is ambiguous: " + filename)
        payload = payload.replace(before, after)
        changes.append((before, after, count))
    inverse = payload
    for before, after, count in reversed(changes):
        if inverse.count(after) != count:
            raise ValueError("literal reader inverse is ambiguous: " + filename)
        inverse = inverse.replace(after, before)
    if inverse != original:
        raise ValueError("whole-source reader inverse differs: " + filename)
    name = "mr3_learning._reach_private_" + uuid.uuid4().hex
    module = ModuleType(name)
    module.__file__, module.__package__ = str(path), "mr3_learning"
    exec(compile(payload, str(path) + "[explicit-reach-dispatch]", "exec"), module.__dict__)
    proof = {"path": str(path), "source_sha256": expected_sha256,
             "projected_sha256": digest(payload), "inverse_sha256": digest(inverse),
             "whole_source_inverse_equal": True,
             "literal_changes": [{"before": a.decode(), "after": b.decode(), "count": n}
                                 for a, b, n in changes],
             "native_inputs_modified": False, "original_module_modified": False}
    return module, proof
