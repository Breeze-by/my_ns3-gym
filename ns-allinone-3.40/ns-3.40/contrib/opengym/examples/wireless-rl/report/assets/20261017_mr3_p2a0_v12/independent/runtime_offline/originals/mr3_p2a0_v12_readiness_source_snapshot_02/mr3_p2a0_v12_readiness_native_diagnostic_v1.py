"""Working-consumer-only diagnostic on unchanged V11 originals; no native run."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
sys.path.insert(0, str(W))
from mr3_learning import audit_controlled_physics as shared


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    output = Path(sys.argv[1])
    episode = ROOT / ('ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/'
                      'mr3_p2a0_20261017_v11_interface/worker0/episode001_open_101')
    old_audit = Path('/tmp/mr3_p2a0_v11_interface_full_audit.json')
    sources = [Path(shared.__file__), W / 'mr3_learning/audit_preparation.py',
               W / 'mr3_learning/audit_ppo.py', Path(__file__)]
    raw = [p for p in episode.iterdir() if p.is_file()]
    before = {str(p): sha(p) for p in raw}
    report = {'passed': False, 'scope': 'working consumer diagnostic only; original V11 '
              'formal FAIL unchanged; no new freeze/native/task/PPO/contact credit',
              'original_formal_fail_sha256': sha(old_audit),
              'consumer_sources': {str(p): sha(p) for p in sources}, 'inputs_before': before}
    began = time.monotonic()
    original_physics = original_readiness = None
    try:
        original = json.loads(old_audit.read_text())
        assert original['passed'] is False
        motion = original['episodes'][0]['motion']
        shared.verify_motion_artifacts(motion)
        scripts = ROOT / 'ros2_ws/ros2-multi-robot-automap/scripts'
        load('ros_smoke_test', scripts / 'ros_smoke_test.py')
        load('audit_mr3_adapter_probe', scripts / 'audit_mr3_adapter_probe.py')
        auditor = load('v12_diagnostic_original_w7', scripts / 'audit_mr3_env.py')
        contact = load('v12_diagnostic_original_contact', W / 'report/assets/20261015_mr3_p1c/'
                       'audit_mr3_env_contact_phase_v2.py')
        report['original_helper_sources'] = {str(Path(m.__file__)): sha(m.__file__)
                                              for m in (auditor, contact)}
        # Existing compatible-loader mechanism selects the actual runtime freeze.
        # No original function code or native metadata/rows is rewritten.
        metadata = json.loads((episode / 'metadata.json').read_text())
        contact.FREEZE = metadata['freeze']
        report['contact_module_freeze_selection'] = contact.FREEZE
        cache = {episode: motion}
        original_readiness = auditor.audit_initial_inputs_ready
        original_physics = shared.dispatch_controlled_physics(auditor, [episode], cache)
        shared.dispatch_controlled_readiness(auditor, [episode], cache)
        report['new_readiness'] = auditor.audit_initial_inputs_ready(
            metadata, shared._rows(episode / 'transitions.jsonl'),
            shared._rows(episode / 'adapter.jsonl'), metadata['epoch'])
        report['original_contact_release_context'] = contact.release_context(auditor, episode)
        report['passed'] = True
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        report['traceback'] = traceback.format_exc()
    finally:
        if original_physics is not None:
            auditor.audit_physics = original_physics
        if original_readiness is not None:
            auditor.audit_initial_inputs_ready = original_readiness
        report['inputs_after'] = {str(p): sha(p) for p in raw}
        report['inputs_unchanged'] = before == report['inputs_after']
        report['original_fail_unchanged'] = sha(old_audit) == report['original_formal_fail_sha256']
        report['sources_unchanged'] = report['consumer_sources'] == {str(p): sha(p) for p in sources}
        report['passed'] = all((report['passed'], report['inputs_unchanged'],
                                report['original_fail_unchanged'], report['sources_unchanged']))
        report['wall_sec'] = time.monotonic() - began
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k: report.get(k) for k in ('passed', 'error', 'wall_sec')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
