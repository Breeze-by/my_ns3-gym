"""V19 saved-identity absence, including the closed reader-interruption roots.

The original A16 absence implementation remains byte-identical. Its required
matrix/native/outer boundary and PID/start lookup rules execute unchanged.
This wrapper extends only Evidence input enumeration and reports the recorded
external SIGINT separately from this absence check's zero signals.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ORIGINAL_SHA = 'cedae11c4b9bbf6f4887ae5afe2fa10fff04e5a28595f5c9e748669c8d18493f'
ORIGINAL = Path(__file__).resolve().parent.parent / '20261019_mr3_p2a_v16/external_absence_v1.py'
SCHEMA = 'mr3-reach-v19-external-process-absence-v2'
sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix', required=True, type=Path)
    parser.add_argument('--outer', required=True, type=Path)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--operator-root', required=True, type=Path)
    parser.add_argument('--operator-wait-root', required=True, type=Path)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    raw = ORIGINAL.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ORIGINAL_SHA:
        raise ValueError('original absence helper SHA differs')
    spec = importlib.util.spec_from_file_location('mr3_v19_original_absence', ORIGINAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_evidence = module.Evidence
    extras = (args.operator_root.resolve(strict=True), args.operator_wait_root.resolve(strict=True))
    if any(not root.is_dir() or args.output.resolve().is_relative_to(root) for root in extras):
        raise ValueError('extra closed roots must be directories outside the output')
    intervention_path = extras[0] / 'intervention.json'
    control_wait_path = extras[1] / 'actual_wait.json'
    plan_path = args.plan.resolve(strict=True)
    plan_raw = plan_path.read_bytes()
    plan = module.parse(plan_raw)
    plan_sha = hashlib.sha256(plan_raw).hexdigest()
    information_jobs = [job for job in plan['stages'][0]['audits'] if job['id'] == 'information']
    if plan['stages'][0]['stage'] != 'interface' or len(information_jobs) != 1:
        raise ValueError('plan has no unique first-stage information job')
    info_receipt_path = Path(information_jobs[0]['receipt'])
    if not info_receipt_path.is_absolute():
        raise ValueError('plan information receipt must be an explicit absolute path')

    def paths():
        return sorted({path for root in extras for path in root.rglob('*')
                       if path.is_file() and (path.suffix in ('.json', '.jsonl')
                                              or path.name == 'console.log')})

    class ExtendedEvidence(original_evidence):
        def __init__(self):
            super().__init__()
            self.extra_paths = paths()
            for path in self.extra_paths:
                try:
                    self.consume(path)
                except (OSError, ValueError, TypeError) as error:
                    self.error(str(path), error)
            for path in (intervention_path, control_wait_path,
                         extras[0] / 'ledger_snapshot_before.jsonl', extras[1] / 'console.log'):
                if path not in self.stat_before:
                    self.error(str(path), 'required closed operator input is missing or unreadable')

        def finish(self):
            super().finish()
            if paths() != self.extra_paths:
                self.error('extra closed roots', 'operator evidence file membership changed')
            try:
                intervention = self.documents[str(intervention_path)]
                wait = self.documents[str(control_wait_path)]
                native = self.documents[str(info_receipt_path)]
                matrix = self.documents[str(args.matrix.resolve(strict=True) / 'summary.json')]
                summary_info = matrix['stages'][0]['audits']['information']
                if (matrix.get('plan_sha256') != plan_sha
                        or summary_info.get('receipt') != str(info_receipt_path)
                        or json.dumps(summary_info, sort_keys=True, allow_nan=False) !=
                           json.dumps(native, sort_keys=True, allow_nan=False)):
                    self.error(str(info_receipt_path), 'plan receipt differs from original summary/actual receipt contents')
                if (intervention.get('schema') != 'mr3-reach-external-reader-interruption-v1'
                        or intervention.get('signal_sent') is not True
                        or intervention.get('signal_name') != 'SIGINT'
                        or intervention.get('errors') != []
                        or intervention.get('scientific_pass_claimed') is not False
                        or intervention.get('freeze') != matrix.get('freeze')):
                    self.error(str(intervention_path), 'recorded external SIGINT identity/status differs')
                if (wait.get('schema') != 'mr3-reach-outer-actual-wait-v1'
                        or wait.get('actual_waited') is not True or wait.get('actual_returncode') != 0
                        or wait.get('passed') is not True or wait.get('source_unchanged') is not True
                        or wait.get('errors') != []
                        or wait.get('actual_argv') != intervention.get('actual_control_argv')):
                    self.error(str(control_wait_path), 'operator command did not actually wait successfully')
                for key in ('pid', 'start_ticks'):
                    if wait['child_identity'][key] != intervention['operator'][key]:
                        self.error(str(control_wait_path), 'actual waited operator identity differs')
                    if native['process_identity'][key] != intervention['target_before'][key]:
                        self.error(str(info_receipt_path), 'interrupted target differs from actual reader child')
                if (native.get('execution_kind') != 'subprocess_waited'
                        or type(native.get('returncode')) is not int or native['returncode'] == 0
                        or native.get('passed') is not False):
                    self.error(str(info_receipt_path), 'interrupted reader lacks its original actual failed wait')
            except (KeyError, TypeError, OSError, ValueError) as error:
                self.error('operator interruption boundary', error)

    module.Evidence = ExtendedEvidence
    result = module.inspect(args)
    original_schema = result['schema']
    result.update(schema=SCHEMA, original_schema=original_schema,
        wrapper_implementation={'path': str(Path(__file__).resolve()),
            'sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'original_path': str(ORIGINAL), 'original_sha256': ORIGINAL_SHA,
            'method': 'unchanged original inspect plus Evidence subclass adding closed inputs/AND checks'},
        recorded_external_intervention={'signal_name': 'SIGINT', 'recorded_signal_count': 1,
            'intervention': str(intervention_path), 'actual_operator_wait': str(control_wait_path),
            'scope': 'one recorded external operator signal; this absence check sends zero signals'},
        absence_check_signals_sent=0,
        information_receipt_resolution={'plan': str(plan_path), 'plan_sha256': plan_sha,
            'selector': "stages[0].audits[id=='information'].receipt",
            'receipt': str(info_receipt_path),
            'original_summary_pointer': '/stages/0/audits/information'},
        enumeration_scope=result['enumeration_scope'] +
            ' Additionally all JSON/JSONL and console.log under the two closed operator roots are byte-bound and consumed by the original Evidence parser; operator, target and wrapper saved PID/start identities join the same strict absence set.',
        run_zero_external_signals_claimed=False)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'schema': SCHEMA, 'passed': result['passed'],
        'identity_count': result['identity_count'], 'present': result['present'],
        'unreadable': result['unreadable'], 'errors': result['errors'], 'output': str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
