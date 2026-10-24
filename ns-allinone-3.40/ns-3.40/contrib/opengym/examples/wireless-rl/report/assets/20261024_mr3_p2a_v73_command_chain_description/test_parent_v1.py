"""V73 parent artificial boundaries; no motion or previous scientific inputs."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('v73_parent',Path(__file__).with_name('run_description_v1.py'))
parent=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(parent)


class ParentBoundaryTests(unittest.TestCase):
    def test_pending_consumer_refuses_before_any_bound_or_git_read(self):
        with patch.object(parent,'CONSUMER_SHA',None),patch.object(parent,'proof') as read,patch.object(parent,'clean_freeze') as git:
            with self.assertRaisesRegex(ValueError,'pending actual V72 description ledger'):
                parent.sources('0'*40,[])
            read.assert_not_called();git.assert_not_called()

    def test_real_closed_description_ledger_is_not_native_qualification(self):
        raw=Path(__file__).with_name('previous_ledger_fixture_v1.json').read_bytes()
        self.assertEqual(len(raw),6593)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'cd620cc88978991f6de366f281e8ce458f07379552abad59ba3886f3319078ab')
        value=json.loads(raw)
        declaration=dict(expected_execution_freeze=parent.PREVIOUS_LEDGER_G,expected_engineering_cumulative_seconds=str(parent.ENTRY))
        parent.validate_previous_ledger(value,declaration)
        changes=[('execution_freeze',parent.EVIDENCE_G),
            ('original_activity_execution_freeze',parent.PREVIOUS_LEDGER_G),('activity_passed',False),
            ('original_activity_passed',{'present':True,'value':True}),('scientific_qualification_credit',True),
            ('actual_root_tool_returncode',False),('capacity_qualified',True)]
        for key,bad in changes:
            altered=copy.deepcopy(value);altered[key]=bad
            with self.subTest(field=key),self.assertRaises(ValueError):parent.validate_previous_ledger(altered,declaration)
        wrong=dict(declaration,expected_execution_freeze=parent.EVIDENCE_G)
        with self.assertRaises(ValueError):parent.validate_previous_ledger(value,wrong)

    def failed_bootstrap(self,original_matches,ended=None):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);owner=parent.identity(os.getpid());saved=dict(owner)
            if not original_matches:saved['start_ticks']+=1
            parent.write(directory/'bootstrap.json',dict(execution_freeze='0'*40,bootstrap_identity=saved,
                complete_parent_started_monotonic_ns=parent.ENTERED_NS))
            with (patch.object(parent,'STATE',directory),
                    patch.object(parent,'sources',side_effect=ValueError('artificial source not admitted')),
                    patch.object(parent,'wait_command') as launch):
                if ended is None:code=parent.execute('0'*40)
                else:
                    with patch.object(parent.time,'monotonic_ns',return_value=ended):code=parent.execute('0'*40)
                self.assertEqual(code,1);launch.assert_not_called()
            return json.loads((directory/'summary.json').read_bytes())

    def test_unverified_identity_never_invents_complete_fee_or_account(self):
        for matches in (False,True):
            with self.subTest(original_identity_matches=matches):
                result=self.failed_bootstrap(matches)
                self.assertFalse(result['passed']);self.assertFalse(result['engineering_entry_verified'])
                self.assertIsNone(result['engineering_cumulative_seconds']);self.assertIsNone(result['engineering_remaining_seconds'])
                self.assertEqual(result['source_before'],[]);self.assertEqual(result['source_after'],[])
                self.assertIsNone(result['consumer']);self.assertEqual(result['raw_input_bytes_read'],0)
                self.assertTrue(result['raw_input_bytes_read_known']);self.assertTrue(result['all_submitted_consumer_waited'])
                self.assertIs(result['complete_parent_fee_known'],matches)
                if matches:self.assertGreaterEqual(float(result['actual_parent_seconds']),0)
                else:self.assertIsNone(result['actual_parent_seconds'])

    def test_actual_full_fee_over300_is_failure_without_child_or_borrowed_account(self):
        value=self.failed_bootstrap(True,parent.ENTERED_NS+301*10**9)
        self.assertEqual(value['actual_parent_seconds'],'301')
        self.assertFalse(value['passed']);self.assertIsNone(value['engineering_cumulative_seconds'])
        self.assertTrue(any('complete parent soft fee cap exceeded' in error for error in value['errors']))
        self.assertEqual(value['complete_parent_cap_seconds'],'300');self.assertEqual(value['consumer_work_seconds'],'240')


if __name__=='__main__':unittest.main()
