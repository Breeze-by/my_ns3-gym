"""Private parent/child JSONL pipes; this module has no ROS or learner imports."""

import json
import os
import selectors
import time


class JsonLinePeer:
    """Bounded synchronous messages, with an absolute wall-clock read guard."""

    def __init__(self, read_fd, write_fd, max_bytes=8 * 1024 * 1024):
        self.read_fd = read_fd
        self.write_fd = write_fd
        self.max_bytes = max_bytes
        self.buffer = bytearray()

    def send(self, message):
        if not isinstance(message, dict):
            raise ValueError("IPC requires an object")
        raw = json.dumps(message, separators=(",", ":"), allow_nan=False).encode() + b"\n"
        if len(raw) > self.max_bytes:
            raise ValueError("IPC message exceeds byte limit")
        while raw:
            written = os.write(self.write_fd, raw)
            if written == 0:
                raise BrokenPipeError("IPC write closed")
            raw = raw[written:]

    def receive(self, timeout):
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            selector.register(self.read_fd, selectors.EVENT_READ)
            while b"\n" not in self.buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise TimeoutError("IPC response wall guard expired")
                chunk = os.read(self.read_fd, 65536)
                if not chunk:
                    raise EOFError("IPC peer closed before a complete response")
                self.buffer.extend(chunk)
                if len(self.buffer) > self.max_bytes:
                    raise ValueError("IPC message exceeds byte limit")
        line, _, remainder = self.buffer.partition(b"\n")
        self.buffer = bytearray(remainder)
        result = json.loads(line)
        if not isinstance(result, dict):
            raise ValueError("IPC response must be an object")
        return result
