"""Private reset deadline/metadata fixtures; never start a native worker."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from mr3_learning import supervisor as module


class StartupReadinessSupervisorTests(unittest.TestCase):
    def test_reach_deadline_starts_before_previous_close_and_worker_creation(self):
        import tempfile
        for contract in ('legacy', 'mr3-reach-v1'):
            with self.subTest(contract=contract), tempfile.TemporaryDirectory() as temporary:
                supervisor = module.Supervisor(output_root=temporary, safety_contract=contract)
                now, requests, timeouts = [100_000_000_000], [], []
                saved_identity = {'pid': 43121, 'parent': 1, 'group': 43121,
                    'session': 43121, 'start_ticks': 123, 'state': 'S'}
                process = Mock(pid=saved_identity['pid'])
                process.stdout.fileno.return_value = 9
                process.stdin.fileno.return_value = 10

                def previous_close():
                    now[0] += 3_000_000_000

                def start_worker(*args, **kwargs):
                    now[0] += 7_000_000_000
                    return process

                def receive(timeout):
                    timeouts.append(timeout)
                    request = requests[-1]
                    return {'id': request['id'], 'epoch': request['epoch'], 'ok': True,
                            'result': {'snapshot': {'epoch': request['epoch']}}}

                peer = SimpleNamespace(send=requests.append, receive=receive)
                with patch.object(module.time, 'monotonic_ns', side_effect=lambda: now[0]), \
                        patch.object(supervisor, 'close', side_effect=previous_close), \
                        patch.object(module.subprocess, 'Popen', side_effect=start_worker), \
                        patch.object(module, 'process_identity', return_value=saved_identity), \
                        patch.object(module, 'JsonLinePeer', return_value=peer), \
                        patch.object(module.threading, 'Thread'), \
                        patch.object(module, 'remember_processes'):
                    try:
                        supervisor.reset(scene='rooms', seed=101)
                        metadata = json.loads((supervisor.episode.directory / 'supervisor_metadata.json').read_text())
                        request = requests[-1]
                        if contract == 'mr3-reach-v1':
                            self.assertEqual(request['startup_readiness_protocol'], 'received-input-pause-drain-v1')
                            self.assertEqual(request['startup_deadline_monotonic_ns'], 520_000_000_000)
                            self.assertEqual(metadata['reset_started_monotonic_ns'], 100_000_000_000)
                            self.assertEqual(metadata['startup_deadline_monotonic_ns'], 520_000_000_000)
                            self.assertEqual(metadata['startup_cleanup_reserve_seconds'], 60.)
                            self.assertEqual(metadata['startup_response_reserve_seconds'], 5.)
                            self.assertEqual(timeouts, [410.])
                        else:
                            self.assertFalse(any(key.startswith('startup_') for key in request))
                            self.assertNotIn('startup_readiness_protocol', metadata)
                            self.assertNotIn('startup_deadline_monotonic_ns', metadata)
                            self.assertEqual(timeouts, [420.])
                    finally:
                        if supervisor.episode is not None:
                            supervisor.episode.output.close()

    def test_parent_recomputes_remaining_after_send_without_extending_absolute_deadline(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            supervisor = module.Supervisor(output_root=temporary, safety_contract='mr3-reach-v1')
            now, waits = [100_000_000_000], []

            def send(request):
                now[0] += 10_000_000_000

            def receive(timeout):
                waits.append(timeout)
                return {'id': 1, 'epoch': 'current', 'ok': True, 'result': 'actual response'}

            supervisor.episode = SimpleNamespace(epoch='current', peer=SimpleNamespace(send=send, receive=receive))
            with patch.object(module.time, 'monotonic_ns', side_effect=lambda: now[0]), \
                    patch.object(module, 'remember_processes'):
                result = supervisor._rpc('reset', timeout=420.,
                    startup_readiness_protocol='received-input-pause-drain-v1',
                    startup_deadline_monotonic_ns=520_000_000_000)
            self.assertEqual(result, 'actual response')
            self.assertEqual(waits, [410.])

    def test_expired_deadline_never_calls_receive_and_is_an_infrastructure_failure(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            supervisor = module.Supervisor(output_root=temporary, safety_contract='mr3-reach-v1')
            receiver, sender = Mock(), Mock()
            supervisor.episode = SimpleNamespace(epoch='current', peer=SimpleNamespace(send=sender,
                                                                                     receive=receiver))
            with patch.object(module.time, 'monotonic_ns', return_value=520_000_000_000), \
                    patch.object(module, 'remember_processes'):
                with self.assertRaisesRegex(module.InfrastructureError, 'absolute wall guard expired'):
                    supervisor._rpc('reset', timeout=420., startup_deadline_monotonic_ns=520_000_000_000)
            receiver.assert_not_called()
            sender.assert_not_called()

    def test_new_reach_startup_cannot_raise_the_original_guard(self):
        with patch.object(Path, 'mkdir') as mkdir:
            with self.assertRaisesRegex(ValueError, 'original 420s'):
                module.Supervisor(safety_contract='mr3-reach-v1', startup_timeout=421.)
        mkdir.assert_not_called()


if __name__ == '__main__':
    unittest.main()
