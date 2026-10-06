import copy
import json
from pathlib import Path

import pytest

from check_p3b5_directional_delay import delay_audit, validate_declaration


def declaration():
    return json.loads(Path(__file__).with_name('p3b5_directional_delay_manifest.json').read_text())


def test_prospective_declaration_has_four_independent_task_interventions():
    validate_declaration(declaration())


@pytest.mark.parametrize('change', ['coupled', 'missing', 'seed', 'ttl', 'deadline', 'capacity'])
def test_declaration_rejects_a_gap_or_changed_protocol(change):
    config = copy.deepcopy(declaration())
    case = config['cases'][0]
    if change == 'coupled':
        config['profiles'][case['profile']]['downlink_delay_sec'] = .5
    elif change == 'missing':
        config['cases'].pop()
    elif change == 'seed':
        case['frozen_contract']['fault_seed'] = 707
    elif change == 'ttl':
        case['frozen_contract']['ttl_sec_by_type']['pose_state'] = 3.
    elif change == 'deadline':
        case['frozen_contract']['navigation_deadline_sec'] = 100
    else:
        case['frozen_contract']['battery_config']['capacity'] = 60
    with pytest.raises(AssertionError):
        validate_declaration(config)


@pytest.mark.parametrize('latency,valid', [(.5, True), (.6, True), (0., False)])
def test_delivered_attempt_must_actually_obey_the_delay(tmp_path, latency, valid):
    ledger = tmp_path/'ledger.jsonl'
    ledger.write_text(json.dumps({'event': 'delivered', 'direction': 'uplink',
                                 'time': 10.+latency, 'tx_time': 10.})+'\n')
    if valid:
        assert delay_audit(ledger, 'uplink', .5)['delivery_attempt_count'] == 1
    else:
        with pytest.raises(AssertionError, match='bypassed'):
            delay_audit(ledger, 'uplink', .5)


def test_absence_of_real_task_deliveries_is_not_protocol_evidence(tmp_path):
    ledger = tmp_path/'ledger.jsonl'
    ledger.write_text('')
    with pytest.raises(AssertionError, match='No actual'):
        delay_audit(ledger, 'uplink', .5)
