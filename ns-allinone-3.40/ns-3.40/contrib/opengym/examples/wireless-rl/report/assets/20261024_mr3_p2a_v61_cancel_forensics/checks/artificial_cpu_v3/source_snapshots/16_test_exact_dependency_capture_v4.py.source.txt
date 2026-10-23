"""Two scan-to-selection-to-dependency cases; all inputs are newly synthetic."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = load('exact_dependency_candidate', 'cancel_window_extract_v4.py')
old = load('exact_dependency_baseline', 'baseline_cancel_window_extract_v3.py')


def target(sequence, clock):
    return dict(schema='mr3-drive-target-v1', epoch=m.EPOCH, robot=m.ROBOT,
                clock_ns=clock, decision_sequence=sequence, linear_x=0.1, angular_z=0.0)


FIRST = target(9, 30000000000)


def receive(sequence, clock, body):
    return dict(kind='initial_encoder_receive', cmd_seq=sequence, sim_time_ns=clock,
                stored_target=body, first_nonzero_received_cmd_seq=9,
                first_nonzero_received_clock_ns=30000000000, first_nonzero_received_target=FIRST)


def command(sequence, clock, body):
    return dict(kind='command_received', cmd_seq=sequence, sim_time_ns=clock,
                target_decision_sequence=body['decision_sequence'], target_clock_ns=body['clock_ns'],
                desired_v=body['linear_x'], desired_w=body['angular_z'])


def actuation(sequence, cmd, clock, body):
    return dict(kind='actuation', cmd_seq=cmd, actuation_seq=sequence, pair_index=0,
                sim_time_ns=clock, target_decision_sequence=body['decision_sequence'],
                target_clock_ns=body['clock_ns'], dt_ns=34000000,
                current_rim_mps=[0.1, 0.1], desired_rim_mps=[0.1, 0.1], applied_rim_mps=[0.1, 0.1],
                alpha=1.0, max_acceleration_mps2=1.0,
                initial_encoder_hold=dict(genuine_consumed_target=body,
                    first_nonzero_received_cmd_seq=9, first_nonzero_received_clock_ns=30000000000,
                    first_nonzero_received_target=FIRST))


def decision(body):
    return dict(kind='reach_decision', sim_time_sec=body['clock_ns']/1e9,
                payload=dict(robot=m.ROBOT, clock_ns=body['clock_ns'], decision_sequence=body['decision_sequence']))


def applied(act, top_clock):
    pair = {key: act[key] for key in ('pair_index', 'current_rim_mps', 'desired_rim_mps',
                                     'applied_rim_mps', 'alpha', 'max_acceleration_mps2')}
    return dict(kind='reach_driver_ingress', sim_time_sec=top_clock/1e9,
                payload=dict(robot=m.ROBOT, kind='applied', message=dict(
                    schema='mr3-drive-applied-v1', epoch=m.EPOCH, robot=m.ROBOT,
                    cmd_seq=act['cmd_seq'], actuation_sequence=act['actuation_seq'],
                    source_clock_ns=act['sim_time_ns'], dt_ns=act['dt_ns'],
                    target=act['initial_encoder_hold']['genuine_consumed_target'], pairs=[pair])))


class ExactDependencyCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mr3-dependency-artificial-')
        self.root = Path(self.temp.name)
        self.serial = 0
        self.limits = dict(total_encoded_bytes=1000000, total_decoded_bytes=1000000,
            line_bytes=100000, lines_per_file=1000, selected_records=1000,
            selected_raw_bytes=1000000, output_bytes=2000000, work_seconds=10)
    def tearDown(self):
        self.temp.cleanup()
    def pipeline(self, module, drivers, motion, limits=None):
        limits = self.limits if limits is None else limits
        selection = module.Selection([module.PRIMARY, module.SECONDARY], limits)
        reports=[]
        for label, rows in (('drive', drivers), ('motion', motion)):
            self.serial += 1
            encoded=[]
            for sequence, original in enumerate(rows, 1):
                row=copy.deepcopy(original)
                row.update(epoch=module.EPOCH, record_sequence=sequence)
                if label=='drive': row['robot']=module.ROBOT
                encoded.append(json.dumps(row, allow_nan=False).encode()+b'\n')
            raw=b''.join(encoded)
            path=self.root/(str(self.serial)+'_'+label+'.jsonl')
            path.write_bytes(raw)
            item=dict(codec='identity', encoded_bytes=len(raw), encoded_sha256=module.sha(raw),
                      decoded_byte_limit=len(raw)+1)
            report=module.scan(path,label,item,selection,time.monotonic()+10,limits)
            self.assertTrue(report['whole_binding_and_parse_complete'])
            self.assertEqual(report['encoded_input_open_count'],1)
            self.assertEqual(report['decoded_scan_pass_count'],1)
            self.assertEqual(report['encoded_parse_read_bytes'],len(raw))
            reports.append(report)
            if label=='drive' and hasattr(selection,'seal_drive_dependencies'):
                selection.seal_drive_dependencies()
        selected=selection.finish()
        return selected,selection,module.unrestored_dependencies(selected),reports

    def test_pre_window_first_latch_and_older_command_guard_are_preserved(self):
        ten,eleven=target(10,42560000000),target(11,42580000000)
        act=actuation(1252,10,42568000000,ten)
        drivers=[receive(9,30000000000,FIRST),command(9,30000000000,FIRST),
                 receive(10,42560000000,ten),command(10,42560000000,ten),act,
                 receive(11,42580000000,eleven),command(11,42580000000,eleven)]
        motion=[decision(ten),decision(eleven),applied(act,42580000000)]
        before,_,missing,_=self.pipeline(old,drivers,motion)
        # v3 already has the eager first-nonzero latch branch; do not invent its absence.
        self.assertTrue(any('original_first_nonzero_receive_latch_dependency' in row['selection_reasons'] for row in before))
        self.assertTrue(any('command_received_not_restored' in reason or 'guard_decision_not_restored' in reason for reason in missing))
        selected,selection,missing,_=self.pipeline(m,drivers,motion)
        self.assertEqual(missing,[])
        self.assertEqual(selection.drops,0)
        latch=[row for row in selected if row['input']=='drive' and json.loads(row['raw_utf8']).get('kind')=='initial_encoder_receive'
               and json.loads(row['raw_utf8']).get('cmd_seq')==9]
        self.assertEqual(len(latch),1)
        self.assertEqual(latch[0]['line_1based'],1)
        self.assertIn('exact_selected_actuation_first_nonzero_dependency',latch[0]['selection_reasons'])
        self.assertTrue(any('exact_selected_actuation_command_dependency' in row['selection_reasons']
                            and json.loads(row['raw_utf8']).get('cmd_seq')==10 for row in selected))
        small=dict(self.limits,selected_records=2)
        _,limited,missing,_=self.pipeline(m,drivers,motion,small)
        self.assertGreater(limited.index_drops,0)
        self.assertGreater(limited.drops,0)
        self.assertTrue(missing)
        self.assertLessEqual(limited.peak_reserved_records,2)

    def test_boundary_after_APPLIED_is_exactly_selected_between_other_receipts(self):
        ten,eleven,twelve=target(10,46060000000),target(11,46100000000),target(12,46120000000)
        acts=[actuation(1355,10,46070000000,ten),actuation(1356,11,46104000000,eleven),
              actuation(1357,12,46138000000,twelve)]
        drivers=[receive(9,30000000000,FIRST),command(9,30000000000,FIRST)]
        for cmd,body,act in zip((10,11,12),(ten,eleven,twelve),acts):
            drivers.extend([receive(cmd,body['clock_ns'],body),command(cmd,body['clock_ns'],body),act])
        motion=[decision(ten),decision(eleven),applied(acts[0],46120000000),decision(twelve),
                applied(acts[1],46140000000),applied(acts[2],46160000000)]
        _,_,missing,_=self.pipeline(old,drivers,motion)
        self.assertIn('actuation:1356:pair:0:exact_APPLIED_target_sequence_clock_pair_not_restored',missing)
        selected,selection,missing,_=self.pipeline(m,drivers,motion)
        self.assertEqual(missing,[])
        self.assertTrue(selection.drive_sealed)
        self.assertEqual(selection.drops,0)
        rows=[row for row in selected if row['input']=='motion'
              and json.loads(row['raw_utf8']).get('payload',{}).get('message',{}).get('actuation_sequence')==1356]
        self.assertEqual(len(rows),1)
        self.assertIn('exact_selected_actuation_APPLIED_dependency',rows[0]['selection_reasons'])
        self.assertEqual(rows[0]['line_1based'],5)
        self.assertEqual(json.loads(rows[0]['raw_utf8'])['sim_time_sec'],46.14)
        self.assertGreater(json.loads(rows[0]['raw_utf8'])['sim_time_sec']*1e9,m.PRIMARY['end_ns'])
        self.assertEqual([row['line_1based'] for row in selected if row['input']=='drive'],
                         sorted(row['line_1based'] for row in selected if row['input']=='drive'))
        corrupted=copy.deepcopy(motion)
        corrupted[4]['payload']['message']['target']['angular_z']=0.2
        _,_,missing,_=self.pipeline(m,drivers,corrupted)
        self.assertIn('actuation:1356:pair:0:exact_APPLIED_target_sequence_clock_pair_not_restored',missing)


if __name__=='__main__':
    unittest.main()
