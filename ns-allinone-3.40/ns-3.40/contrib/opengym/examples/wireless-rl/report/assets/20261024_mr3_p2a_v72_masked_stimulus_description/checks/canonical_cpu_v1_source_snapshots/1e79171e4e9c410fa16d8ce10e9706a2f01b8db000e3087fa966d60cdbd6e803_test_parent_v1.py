"""Artificial source/admission failures only; never reads either original input."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('v72_parent',Path(__file__).with_name('run_description_v1.py'))
parent=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(parent)


class ParentFailureTests(unittest.TestCase):
    def test_pending_actual_ledger_rejects_before_any_bound_file_or_git(self):
        with patch.object(parent,'LEDGER_SHA',None),patch.object(parent,'proof') as read,patch.object(parent,'clean_freeze') as git:
            with self.assertRaisesRegex(ValueError,'pending actual V71 ledger'):
                parent.sources('0'*40,[])
            read.assert_not_called();git.assert_not_called()

    def test_bootstrap_identity_and_unknown_accounting_are_preserved(self):
        for original_matches in (False,True):
            with self.subTest(original_matches=original_matches),tempfile.TemporaryDirectory() as tmp:
                directory=Path(tmp);owner=parent.identity(os.getpid());saved=dict(owner)
                if not original_matches:saved['start_ticks']+=1
                parent.write(directory/'bootstrap.json',dict(execution_freeze='0'*40,bootstrap_identity=saved,
                    complete_parent_started_monotonic_ns=parent.ENTERED_NS))
                with (patch.object(parent,'STATE',directory),
                        patch.object(parent,'sources',side_effect=ValueError('artificial source not admitted')),
                        patch.object(parent,'wait_command') as launch):
                    self.assertEqual(parent.execute('0'*40),1)
                    launch.assert_not_called()
                result=json.loads((directory/'summary.json').read_bytes())
                self.assertFalse(result['passed']);self.assertFalse(result['engineering_entry_verified'])
                self.assertIsNone(result['engineering_cumulative_seconds']);self.assertIsNone(result['engineering_remaining_seconds'])
                self.assertEqual(result['source_before'],[]);self.assertEqual(result['source_after'],[])
                self.assertIsNone(result['consumer']);self.assertEqual(result['raw_input_bytes_read'],0)
                self.assertTrue(result['raw_input_bytes_read_known']);self.assertTrue(result['all_submitted_consumer_waited'])
                self.assertIs(result['complete_parent_fee_known'],original_matches)
                if original_matches:self.assertGreaterEqual(float(result['actual_parent_seconds']),0)
                else:self.assertIsNone(result['actual_parent_seconds'])


if __name__=='__main__':unittest.main()
