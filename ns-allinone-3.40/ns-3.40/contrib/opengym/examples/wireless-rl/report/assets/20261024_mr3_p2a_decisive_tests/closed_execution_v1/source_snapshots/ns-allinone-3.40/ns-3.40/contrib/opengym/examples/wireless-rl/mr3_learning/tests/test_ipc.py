import contextlib
import os
import time
import unittest
from unittest.mock import patch

from mr3_learning.ipc import JsonLinePeer


@contextlib.contextmanager
def pipe_peer(max_bytes=1024):
    reader, writer = os.pipe()
    try:
        yield JsonLinePeer(reader, writer, max_bytes=max_bytes), reader, writer
    finally:
        for descriptor in (reader, writer):
            try:
                os.close(descriptor)
            except OSError:
                pass


class PipeTests(unittest.TestCase):
    def test_json_line_round_trip_survives_fragmented_reads_and_preserves_next_frame(self):
        with pipe_peer() as (peer, reader, writer):
            message = {"id": 1, "epoch": "episode-a", "payload": [True, None, "机器人"]}
            peer.send(message)
            original_read = os.read
            with patch("mr3_learning.ipc.os.read",
                       side_effect=lambda fd, count: original_read(fd, min(count, 3))):
                self.assertEqual(peer.receive(.5), message)
            os.write(writer, b'{"id":2}\n{"id":3}\n')
            self.assertEqual(peer.receive(.5), {"id": 2})
            self.assertEqual(peer.receive(.5), {"id": 3})

    def test_eof_with_partial_frame_is_an_error(self):
        with pipe_peer() as (peer, reader, writer):
            os.write(writer, b'{"unfinished":')
            os.close(writer)
            with self.assertRaises(EOFError):
                peer.receive(.5)

    def test_no_input_has_a_wall_guard(self):
        with pipe_peer() as (peer, reader, writer):
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                peer.receive(.02)
            self.assertLess(time.monotonic() - started, 1.)

    def test_oversize_is_rejected_on_send_and_receive(self):
        with pipe_peer(max_bytes=32) as (peer, reader, writer):
            with self.assertRaisesRegex(ValueError, "byte limit"):
                peer.send({"payload": "x" * 40})
            os.write(writer, b"x" * 33)
            with self.assertRaisesRegex(ValueError, "byte limit"):
                peer.receive(.5)

    def test_non_object_or_invalid_json_is_rejected(self):
        for frame in (b"[]\n", b"{bad-json}\n"):
            with pipe_peer() as (peer, reader, writer):
                os.write(writer, frame)
                with self.assertRaises(ValueError):
                    peer.receive(.5)

    def test_send_refuses_nonfinite_numbers_and_non_objects(self):
        with pipe_peer() as (peer, reader, writer):
            for value in ({"loss": float("nan")}, {"loss": float("inf")}, [1, 2]):
                with self.assertRaises(ValueError):
                    peer.send(value)
            peer.send({"still_usable": True})
            self.assertEqual(peer.receive(.5), {"still_usable": True})


if __name__ == "__main__":
    unittest.main()
