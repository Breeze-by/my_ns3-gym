"""Lossless array encoding shared by the explicitly separate proxy processes."""
import base64
import hashlib
import json

import numpy as np


def encode_arrays(value):
    if isinstance(value, np.ndarray):
        array = np.ascontiguousarray(value)
        if array.dtype.kind not in "biuf" or array.dtype.hasobject:
            raise ValueError("only numeric proxy arrays may cross IPC")
        return {"__ndarray__": True, "dtype": array.dtype.str,
                "shape": list(array.shape), "data": base64.b64encode(array.tobytes()).decode()}
    if isinstance(value, dict):
        return {key: encode_arrays(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode_arrays(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def decode_arrays(value):
    if isinstance(value, dict) and value.get("__ndarray__") is True:
        if set(value) != {"__ndarray__", "dtype", "shape", "data"}:
            raise ValueError("unknown array fields")
        dtype = np.dtype(value["dtype"])
        shape = value["shape"]
        if (dtype.kind not in "biuf" or dtype.hasobject or len(shape) > 4
                or any(type(n) is not int or n < 0 for n in shape)
                or np.prod(shape, dtype=np.int64) > 2_000_000):
            raise ValueError("invalid proxy array declaration")
        raw = base64.b64decode(value["data"], validate=True)
        expected = int(np.prod(shape)) * dtype.itemsize
        if len(raw) != expected:
            raise ValueError("proxy array byte length mismatch")
        array = np.frombuffer(raw, dtype=dtype).reshape(shape).copy()
        if not np.all(np.isfinite(array)):
            raise ValueError("nonfinite proxy array")
        return array
    if isinstance(value, dict):
        return {key: decode_arrays(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode_arrays(item) for item in value]
    return value


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def tensor_proofs(observation):
    return {name: {"dtype": str(array.dtype), "shape": list(array.shape),
                   "sha256": hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()}
            for name, array in observation.items()}
