#!/usr/bin/env python3
"""Pure stdlib actual-SDF fixtures; no launch/ROS/Gazebo imports or execution."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import subprocess
import unittest
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

HERE = Path(__file__).parent
ROOT = Path('/home/zhuyulab/ns3-workspace')
MODEL = ROOT / 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/models/turtlebot3_waffle/model.sdf'

def load(raw, label):
    source = ast.parse(raw)
    selected = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in
                {'diagnostic_read', 'diagnostic_json', 'prepare_physics_diagnostic',
                 'append_physics_observer', 'append_ray_provenance', 'drive_spawn_model'}]
    namespace = {'Path': Path, 'os': os, 'hashlib': hashlib, 'json': json, 'ET': ET,
                 'escape': escape, 'tempfile': tempfile}
    exec(compile(ast.Module(body=selected, type_ignores=[]), label, 'exec'), namespace)
    return namespace

class Fixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mr3_v21_ray_CPU_')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.run = self.base / 'run'
        self.episode = self.run / 'worker0/episode001_open_101'
        self.episode.mkdir(parents=True)
        self.prefix = self.base / 'install/multi_robot'
        (self.prefix / 'lib').mkdir(parents=True)
        self.specs = {}
        for key, filename in [('observer_library', 'libmr3_stop_response_observer.so'),
                              ('profile_library', 'libmr3_physics_diagnostic_profile.so'),
                              ('ray', 'libmr3_ray_provenance_observer.so')]:
            path = self.prefix / 'lib' / filename
            path.write_bytes(('CPU-only non-executable fixture:' + filename).encode())
            self.specs[key] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                               'source_sha256': 'a' * 64}
        self.world = self.base / 'p1c_open.world'
        self.world.write_text('<sdf version="1.6"><world name="p1c_open"/></sdf>')
        self.path = self.base / 'config.json'
        self.config = {'schema': 'mr3-physics-diagnostic-config-v1', 'run_directory': str(self.run),
          'episode_relative_directory': 'worker0/episode001_open_101', 'scene': 'open', 'seed': 101,
          'mode': 'iters150', 'capture_start_ns': 0, 'capture_end_ns': 300000000000,
          'observer_library': self.specs['observer_library'], 'profile_library': self.specs['profile_library']}
        original = HERE / 'launch_original.py'
        relative = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py'
        self.old_source = original.read_text() if original.exists() else subprocess.check_output(
            ['git', 'show', '4f8bd0e509e6f958c5993a50008955afac72c345:' + relative], cwd=ROOT, text=True)
        proposed = HERE / 'proposed_launch.py'
        self.new_source = proposed.read_text() if proposed.exists() else (ROOT / relative).read_text()
        self.old = load(self.old_source, 'original_launch')
        self.new = load(self.new_source, 'proposed_launch')

    def ray(self):
        spec = self.specs['ray']
        return {'enabled': True, 'library': spec['path'], 'library_sha256': spec['sha256'],
                'source_sha256': spec['source_sha256'], 'start_ns': 0, 'end_ns': 300000000000,
                'sensor_link': 'base_scan', 'sensor_name': 'hls_lfcd_lds'}

    def prepare(self, namespace, config):
        self.path.write_text(json.dumps(config))
        return namespace['prepare_physics_diagnostic'](str(self.path), adapter_mode=True, stepped_mode=True,
          robot_count=3, epoch='CPU_fixture_epoch', audit_path=str(self.episode / 'adapter.jsonl'),
          world=str(self.world), seed=101, package_prefix=str(self.prefix))

    def test_legacy_binding_and_real_spawn_bytes_equal(self):
        old = self.prepare(self.old, self.config)
        binding = Path(old['binding_path'])
        original_binding = binding.read_bytes()
        binding.rename(binding.with_name('old_binding.json'))
        new = self.prepare(self.new, self.config)
        self.assertEqual(new, old)
        self.assertEqual(binding.read_bytes(), original_binding)
        for robot in ('tb1', 'tb2', 'tb3'):
            args = (str(MODEL), robot, str(self.episode / 'adapter.jsonl'), 'CPU_fixture_epoch', True)
            original = Path(self.old['drive_spawn_model'](*args, physics_diagnostic=old))
            raw = original.read_bytes()
            original.rename(original.with_suffix('.old'))
            rendered = Path(self.new['drive_spawn_model'](*args, physics_diagnostic=new)).read_bytes()
            self.assertEqual(rendered, raw)
        self.assertIsNone(self.new['prepare_physics_diagnostic']('', adapter_mode=False,
          stepped_mode=False, robot_count=4, epoch='', audit_path='', world='', seed=0, package_prefix=''))

    def test_ray_appends_only_fixed_plugin_to_actual_model(self):
        config = {**self.config, 'ray_provenance': self.ray()}
        selected = self.prepare(self.new, config)
        for robot in ('tb1', 'tb2', 'tb3'):
            path = self.new['drive_spawn_model'](str(MODEL), robot, str(self.episode / 'adapter.jsonl'),
              'CPU_fixture_epoch', True, physics_diagnostic=selected)
            rendered = Path(path).read_text()
            expected_base = self.new['append_physics_observer'](MODEL.read_text(), robot, selected)
            # Drive audit tags are the same preexisting replacements in both versions.
            for tag, value in {'mr3_audit_path': str(self.episode / f'drive_{robot}.jsonl'),
              'mr3_epoch': 'CPU_fixture_epoch', 'mr3_tagged_commands': 'true'}.items():
                expected_base = expected_base.replace(f'<{tag}/>', f'<{tag}>{escape(value)}</{tag}>')
            marker = f'        <plugin name="mr3_ray_provenance_observer_{robot}"'
            start = rendered.index(marker)
            end = rendered.index('        </plugin>\n', start) + len('        </plugin>\n')
            self.assertEqual(rendered[:start] + rendered[end:], expected_base)
            tree = ET.fromstring(rendered)
            sensor = tree.find("model/link[@name='base_scan']/sensor[@name='hls_lfcd_lds']")
            plugin = sensor.find(f"plugin[@name='mr3_ray_provenance_observer_{robot}']")
            self.assertEqual(plugin.get('filename'), self.specs['ray']['path'])
            self.assertEqual({p.tag: p.text for p in plugin}, {
              'output_path': str(self.episode / f'ray_{robot}.jsonl'), 'epoch': 'CPU_fixture_epoch',
              'robot': robot, 'sensor_link': 'base_scan', 'sensor_name': 'hls_lfcd_lds',
              'start_ns': '0', 'end_ns': '300000000000'})
            sensor.remove(plugin)
            original_sensor = ET.fromstring(MODEL.read_bytes()).find("model/link[@name='base_scan']/sensor[@type='ray']")
            self.assertEqual(sensor.attrib, original_sensor.attrib)
            self.assertEqual(ET.tostring(sensor.find('ray')), ET.tostring(original_sensor.find('ray')))
            self.assertEqual(sensor.findtext('pose'), original_sensor.findtext('pose'))

    def test_wrong_path_digest_sensor_window_or_unknown_fields_refused(self):
        cases = []
        for key, value in [('enabled', False), ('enabled', 1), ('library', '/tmp/arbitrary.so'),
                           ('library_sha256', '0' * 64), ('source_sha256', 'A' * 64),
                           ('sensor_name', 'other'), ('sensor_link', 'base_link'),
                           ('start_ns', False), ('end_ns', 300000000001), ('unknown', 1)]:
            ray = self.ray(); ray[key] = value; cases.append(ray)
        for ray in cases:
            with self.subTest(ray=ray):
                with self.assertRaises((ValueError, FileNotFoundError)):
                    self.prepare(self.new, {**self.config, 'ray_provenance': ray})
                self.assertFalse((self.episode / 'physics_diagnostic_binding.json').exists())

    def test_duplicate_disabled_robot_and_ambiguous_model_refused(self):
        diagnostic = self.prepare(self.new, {**self.config, 'ray_provenance': self.ray()})
        raw = MODEL.read_text()
        rendered = self.new['append_ray_provenance'](raw, 'tb1', diagnostic)
        for model, robot in [(rendered, 'tb1'), (raw, 'tb4'), (raw + '</model>', 'tb1')]:
            with self.assertRaises(ValueError): self.new['append_ray_provenance'](model, robot, diagnostic)

    def test_short_old_observer_window_does_not_shorten_ray_window(self):
        config = {**self.config, 'capture_end_ns': 1000000, 'ray_provenance': self.ray()}
        diagnostic = self.prepare(self.new, config)
        raw = self.new['append_physics_observer'](MODEL.read_text(), 'tb1', diagnostic)
        rendered = self.new['append_ray_provenance'](raw, 'tb1', diagnostic)
        model = ET.fromstring(rendered).find('model')
        self.assertEqual(model.findtext("plugin[@name='mr3_stop_response_observer_tb1']/end_ns"), '1000000')
        self.assertEqual(model.findtext("link[@name='base_scan']/sensor[@name='hls_lfcd_lds']/plugin[@name='mr3_ray_provenance_observer_tb1']/end_ns"), '300000000000')

    def test_other_launch_functions_and_original_system_args_unchanged(self):
        old = ast.parse(self.old_source)
        new = ast.parse(self.new_source)
        ignored = {'prepare_physics_diagnostic', 'drive_spawn_model', 'append_ray_provenance'}
        def normalized(tree):
            return ast.dump(ast.Module(body=[n for n in tree.body if not
              ((isinstance(n, ast.FunctionDef) and n.name in ignored) or
               (isinstance(n, ast.Import) and any(a.name == 'xml.etree.ElementTree' for a in n.names)))],
               type_ignores=[]), include_attributes=False)
        self.assertEqual(normalized(old), normalized(new))

if __name__ == '__main__': unittest.main()
