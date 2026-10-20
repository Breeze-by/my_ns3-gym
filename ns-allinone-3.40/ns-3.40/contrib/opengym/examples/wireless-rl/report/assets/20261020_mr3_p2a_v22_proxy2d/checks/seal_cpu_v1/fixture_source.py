import ast, importlib.util, io, json, lzma, os, random, tarfile, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
SCRIPT=Path(__file__).resolve().parents[2]/'seal_results_v1.py'
ast.parse(SCRIPT.read_bytes()); compile(SCRIPT.read_bytes(),str(SCRIPT),'exec')
spec=importlib.util.spec_from_file_location('seal_fixture_subject',SCRIPT)
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
class SealFixtures(unittest.TestCase):
 def sources(self,base):
  run=base/'run';run.mkdir();(run/'nested/empty').mkdir(parents=True)
  (run/'payload.bin').write_bytes(random.Random(7).randbytes(9000))
  os.link(run/'payload.bin',run/'nested/hardlink.bin')
  (run/'failure.json').write_text('{"passed":false,"actual_returncode":1}\n')
  (run/'zero').touch()
  outer=base/'outer.json';outer.write_text('{"actual_returncode":1}\n')
  tree=base/'consumer';(tree/'empty').mkdir(parents=True);(tree/'evidence.txt').write_text('FAIL retained\n')
  extra=base/'wait.log';extra.write_text('actual waited\n')
  return run,outer,tree,extra,base/'sealed'
 def test_full_seal_split_all_bytes_hardlinks_exact_copies_and_fail_retained(self):
  with tempfile.TemporaryDirectory() as tmp:
   run,outer,tree,extra,out=self.sources(Path(tmp));before=s.inventory(run)
   result=s.seal(run,out,[outer],[tree,extra],part_bytes=512)
   self.assertEqual(s.inventory(run),before);self.assertTrue(result['byte_verification_passed'])
   self.assertEqual(result['run_file_count'],4);self.assertEqual(result['auxiliary_file_count'],3)
   self.assertGreater(len(result['parts']),1);self.assertTrue(all(x['bytes']==512 for x in result['parts'][:-1]))
   payload=b''.join((out/x['path']).read_bytes() for x in result['parts'])
   self.assertEqual(__import__('hashlib').sha256(payload).hexdigest(),result['archive_sha256'])
   with tarfile.open(fileobj=io.BytesIO(lzma.decompress(payload)),mode='r:') as archive:
    members={m.name.removeprefix('./'):m for m in archive if m.isfile()}
    self.assertEqual(set(members),set(before['files']))
    for name,member in members.items():self.assertEqual(archive.extractfile(member).read(),(run/name).read_bytes())
   self.assertFalse(json.loads((out/'closed_execution/aux/outer.json').read_text()).get('passed',False))
   self.assertEqual(json.loads((out/'closed_execution/aux/outer.json').read_text())['actual_returncode'],1)
   for entry in json.loads((out/'auxiliary_copy_index_v1.json').read_text())['files']:
    self.assertEqual(Path(entry['original']).read_bytes(),(out/entry['copy']).read_bytes())
   manifest=json.loads((out/'archive_manifest_v1.json').read_text())
   for ref in manifest['metadata']:
    self.assertEqual(s.digest(out/ref['path']),ref['sha256'])
   self.assertFalse(result['qualification']);self.assertFalse(result['training_eligible']);self.assertFalse(result['native_credit'])
 def test_cli_explicit_paths_uses_fixed_32mib_parts(self):
  with tempfile.TemporaryDirectory() as tmp:
   run,outer,tree,extra,out=self.sources(Path(tmp))
   self.assertEqual(s.main(['--run',str(run),'--outer',str(outer),'--copy',str(tree),'--output',str(out)]),0)
   self.assertEqual(json.loads((out/'archive_verification_v1.json').read_text())['part_bytes'],32*1024*1024)
 def test_missing_explicit_paths_does_not_run(self):
  with self.assertRaises(SystemExit) as cm:s.main([])
  self.assertEqual(cm.exception.code,2)
 def test_existing_outputs_are_not_overwritten(self):
  with tempfile.TemporaryDirectory() as tmp:
   run,outer,tree,extra,out=self.sources(Path(tmp));out.mkdir();path=out/'run.tar.xz.part0001';path.write_bytes(b'preserve')
   with self.assertRaisesRegex(ValueError,'already exist'):s.seal(run,out,[outer])
   self.assertEqual(path.read_bytes(),b'preserve');self.assertEqual(list(out.iterdir()),[path])
 def test_nested_run_symlink_rejected_and_failure_preserved(self):
  with tempfile.TemporaryDirectory() as tmp:
   run,outer,tree,extra,out=self.sources(Path(tmp));(run/'link').symlink_to(run/'payload.bin')
   with self.assertRaisesRegex(ValueError,'regular file'):s.seal(run,out,[outer])
   self.assertTrue((run/'link').is_symlink());self.assertTrue((out/'seal_failure_v1.json').is_file())
   self.assertFalse((out/'archive_manifest_v1.json').exists())
 def test_run_root_symlink_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);run,outer,tree,extra,out=self.sources(base);link=base/'alias';link.symlink_to(run,target_is_directory=True)
   with self.assertRaisesRegex(ValueError,'symlink'):s.seal(link,out,[outer])
   self.assertFalse(out.exists())
 def test_fifo_rejected_without_opening_it(self):
  with tempfile.TemporaryDirectory() as tmp:
   run,outer,tree,extra,out=self.sources(Path(tmp));os.mkfifo(run/'fifo')
   with self.assertRaisesRegex(ValueError,'regular file'):s.seal(run,out,[outer])
 def test_auxiliary_symlink_and_destination_collision_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);run,outer,tree,extra,out=self.sources(base);link=base/'link';link.symlink_to(outer)
   with self.assertRaisesRegex(ValueError,'symlink'):s.seal(run,out,[link])
   other=base/'other';other.mkdir();(other/outer.name).write_bytes(b'other')
   with self.assertRaisesRegex(ValueError,'basename collision'):s.seal(run,out,[outer],[other/outer.name])
 def test_nested_auxiliary_symlink_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   run,outer,tree,extra,out=self.sources(Path(tmp));(tree/'bad').symlink_to(extra)
   with self.assertRaisesRegex(ValueError,'regular file'):s.seal(run,out,[outer],[tree])
   self.assertTrue((tree/'bad').is_symlink());self.assertFalse((out/'archive_manifest_v1.json').exists())
 def test_archive_corruption_and_missing_member_detected(self):
  with tempfile.TemporaryDirectory() as tmp:
   run,outer,tree,extra,out=self.sources(Path(tmp));result=s.seal(run,out,[outer],part_bytes=512)
   paths=[out/x['path'] for x in result['parts']];expected=s.inventory(run)['files']
   with self.assertRaisesRegex(ValueError,'omitted'):s.verify_members(paths,{**expected,'notpresent':{'bytes':0,'sha256':'0'*64}})
   raw=paths[0].read_bytes();paths[0].write_bytes(b'broken!'+raw[7:])
   with self.assertRaises((lzma.LZMAError,EOFError,tarfile.ReadError)):s.verify_members(paths,expected)
 def test_run_change_after_archive_verification_prevents_pass(self):
  with tempfile.TemporaryDirectory() as tmp:
   run,outer,tree,extra,out=self.sources(Path(tmp));original=s.verify_members
   def changed(*args):
    result=original(*args);(run/'failure.json').write_text('changed');return result
   with patch.object(s,'verify_members',side_effect=changed),self.assertRaisesRegex(ValueError,'originals changed'):s.seal(run,out,[outer])
   self.assertTrue((out/'seal_failure_v1.json').exists());self.assertFalse((out/'archive_verification_v1.json').exists())
 def test_auxiliary_change_before_verdict_prevents_pass(self):
  with tempfile.TemporaryDirectory() as tmp:
   run,outer,tree,extra,out=self.sources(Path(tmp));original=s.exact_copy
   def changed(*args):
    result=original(*args);outer.write_text('changed');return result
   with patch.object(s,'exact_copy',side_effect=changed),self.assertRaisesRegex(ValueError,'auxiliary originals changed'):s.seal(run,out,[outer])
   self.assertTrue((out/'seal_failure_v1.json').exists());self.assertFalse((out/'archive_manifest_v1.json').exists())
if __name__=='__main__':unittest.main()
