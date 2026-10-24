#!/usr/bin/env python3
"""V11 sticky-negative extension of the exact frozen V10 control reader.

Only actual worker ACK callbacks gain a check. All geometry, protocol, bootstrap,
stop, source-clock, local receipt and native-storage replay remains in the
SHA-pinned original reader. Neither file imports production control code.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

OLD_SHA = '04cd7d079c16004b20320868943bcdac899da7646304d30cbad0804d1a6ee8d3'
OLD_RELATIVE = Path('20261017_mr3_p2a0_v10/independent/mr3_independent_control_phase_v1.py')
ROOT = Path('/home/zhuyulab/ns3-workspace')
CANDIDATES = ([Path(__file__).resolve().parents[2] / OLD_RELATIVE]
              if len(Path(__file__).resolve().parents) > 2 else [])
CANDIDATES.append(ROOT / ('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/'
                          'wireless-rl/report/assets') / OLD_RELATIVE)
OLD_PATH = next(path for path in CANDIDATES if path.is_file()
                and hashlib.sha256(path.read_bytes()).hexdigest() == OLD_SHA)
SPEC = importlib.util.spec_from_file_location('v11_pinned_v10_control_reader', OLD_PATH)
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)


def check_sticky_negative_callback(row, epoch):
    """A stop/abandonment never erases an actual nonterminal producer error.

    The sole terminal exception still passes through the original reader, which
    binds it to the actual prior information notice, exact ACK bytes and scope.
    This predicate alone never grants that exception or any successful receipt.
    """
    if row.get('kind') != 'ack_received':
        return
    ack = row.get('ack')
    BASE.require(type(ack) is dict, 'actual worker ACK must be an object')
    if ack.get('epoch') != epoch:
        return  # Original ignored cross-epoch callback; cannot be consumed.
    BASE.require(type(ack.get('ok')) is bool, 'actual worker ACK ok must be typed boolean')
    if ack['ok']:
        return
    terminal_candidate = (row.get('component') == 'state'
                          and ack.get('error') == 'state_phase_task_terminal'
                          and ack.get('scope') == 'terminal_cancelled_uncommitted_state_phase'
                          and type(ack.get('terminal_notice')) is dict)
    BASE.require(terminal_candidate,
                 'actual nonterminal negative ACK is a real control failure '
                 '(sticky, including abandoned requests)')


OriginalControlReplay = BASE.ControlReplay


class StickyControlReplay(OriginalControlReplay):
    def record(self, row):
        check_sticky_negative_callback(row, self.epoch)
        return super().record(row)


# The inherited audit_episode looks up this class at replay time. The isolated
# imported module is patched, not its original file or any other consumer.
BASE.ControlReplay = StickyControlReplay


def audit_episode(directory, freeze, peer_only=False):
    return BASE.audit_episode(directory, freeze, peer_only)


def audit(directory, freeze, peer_only=False):
    result = BASE.audit(directory, freeze, peer_only)
    result['schema'] = 'mr3-independent-controlled-execution-review-v2'
    result['consumer_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result['inherited_reader'] = {'path': str(OLD_PATH), 'sha256': OLD_SHA,
                                  'all_original_rules_retained': True}
    sticky_key = 'actual_nonterminal_negative_ack_sticky_including_abandoned'
    result['criteria'][sticky_key] = not peer_only
    result['limitations'].append(
        'Only the full-control mode applies the worker ACK-prefix extension; '
        'peer-only retains its original overlapping component scope.')
    if hashlib.sha256(OLD_PATH.read_bytes()).hexdigest() != OLD_SHA:
        result['passed'] = False
        result['errors'].append('pinned inherited reader changed during replay')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--peer-only', action='store_true')
    args = parser.parse_args()
    result = audit(args.directory, args.freeze, args.peer_only)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(json.dumps({'passed': result['passed'], 'mode': result['mode'],
                      'episodes': len(result['episodes']), 'output': str(args.output)},
                     sort_keys=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
