"""Focused stdlib SensorPlugin witness contract fixtures; no native/DDS/proc mutation."""
import copy
import importlib.util
from pathlib import Path
import unittest
from xml.sax.saxutils import escape
import test_launch_ray_binding as launch_fixture

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('ray_witness', HERE/'mr3_p2a0_v21_ray_live_admission_v1.py')
witness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(witness)


class WitnessFixtures(unittest.TestCase):
    setUp = launch_fixture.Fixtures.setUp
    ray = launch_fixture.Fixtures.ray
    prepare = launch_fixture.Fixtures.prepare

    def rendered(self):
        selected = self.prepare(self.new, {**self.config, 'capture_end_ns': 1000000,
                                          'ray_provenance': self.ray()})
        rendered = Path(self.new['drive_spawn_model'](str(launch_fixture.MODEL), 'tb1',
            str(self.episode/'adapter.jsonl'), 'CPU_fixture_epoch', True,
            physics_diagnostic=selected)).read_bytes()
        base = launch_fixture.MODEL.read_text()
        for tag, value in {'mr3_audit_path': str(self.episode/'drive_tb1.jsonl'),
                           'mr3_epoch': 'CPU_fixture_epoch', 'mr3_tagged_commands': 'true'}.items():
            base = base.replace(f'<{tag}/>', f'<{tag}>{escape(value)}</{tag}>')
        return rendered, selected['binding'], base

    def test_both_plugins_exact_inverse_with_short_physics_window(self):
        rendered, binding, base = self.rendered()
        self.assertEqual(witness.project_actual_model(rendered, binding, 'tb1', base), base.encode())

    def test_wrong_source_path_elf_and_header_refused(self):
        selected = self.prepare(self.new, {**self.config, 'ray_provenance': self.ray()})
        ray = selected['binding']['ray_provenance']
        # A fake ELF byte fixture is never loaded or executed.
        library = Path(ray['resolved_path']); library.write_bytes(b'\x7fELFfake CPU fixture')
        ray['library_sha256'] = witness.sha(library.read_bytes())
        expected = {'installed_path': ray['library'], 'installed_resolved_path': ray['resolved_path'],
                    'source_sha256': ray['source_sha256'], 'library_sha256': ray['library_sha256'],
                    'library_bytes': library.stat().st_size}
        self.assertEqual(witness.verify_ray_library(ray, expected)['library_sha256'], ray['library_sha256'])
        for field, value in [('source_sha256', 'b'*64), ('library', '/tmp/wrong.so'),
                             ('library_sha256', 'b'*64), ('resolved_path', '/tmp/wrong.so')]:
            with self.subTest(field=field):
                changed = {**ray, field: value}
                with self.assertRaises((ValueError, FileNotFoundError)):
                    witness.verify_ray_library(changed, expected)
        header = {'schema': 'mr3-ray-provenance-audit-v1', 'kind': 'configuration',
                  'plugin_type': 'SensorPlugin', 'robot': 'tb1', 'epoch': 'CPU_fixture_epoch',
                  'process_id': 1234, 'compiled_source_sha256': ray['source_sha256'],
                  'loaded_library_path': ray['resolved_path'],
                  'scope': 'Passive diagnostic only; no publish, physics/sensor setter, ray update/recast, actor input or task credit.'}
        witness.validate_ray_configuration(header, ray, 'tb1', 'CPU_fixture_epoch')
        for field, value in [('plugin_type','ModelPlugin'), ('process_id',True), ('robot','tb2'),
                             ('epoch','other'), ('compiled_source_sha256','b'*64),
                             ('loaded_library_path','/tmp/other.so'), ('scope','claimed read only')]:
            with self.subTest(header_field=field), self.assertRaises(ValueError):
                witness.validate_ray_configuration({**header,field:value},ray,'tb1','CPU_fixture_epoch')
        library.write_bytes(b'not an ELF')
        ray['library_sha256'] = expected['library_sha256'] = witness.sha(library.read_bytes())
        expected['library_bytes'] = library.stat().st_size
        with self.assertRaises(ValueError): witness.verify_ray_library(ray, expected)

    def test_wrong_placement_duplicate_or_extra_child_refused(self):
        rendered, binding, base = self.rendered()
        raw = rendered.decode(); name = 'mr3_ray_provenance_observer_tb1'
        start = raw.index('        <plugin name="'+name+'"')
        end = raw.index('        </plugin>\n',start)+len('        </plugin>\n')
        block = raw[start:end]
        cases = [raw.replace(block, block+block),
                 raw.replace(block, block.replace('<robot>tb1</robot>','<robot>tb2</robot>')),
                 raw.replace(block, block.replace('</plugin>','<extra/>\n        </plugin>')),
                 raw.replace(block, block.replace('<robot>tb1</robot>','<robot>tb1</robot><robot>tb1</robot>')),
                 raw.replace(block, '').replace('</model>',block+'</model>'),
                 raw.replace(block, block.replace(binding['ray_provenance']['library'],'/tmp/wrong.so'))]
        for number, changed in enumerate(cases):
            with self.subTest(case=number), self.assertRaises(ValueError):
                witness.project_actual_model(changed.encode(),binding,'tb1',base)


if __name__ == '__main__': unittest.main()
