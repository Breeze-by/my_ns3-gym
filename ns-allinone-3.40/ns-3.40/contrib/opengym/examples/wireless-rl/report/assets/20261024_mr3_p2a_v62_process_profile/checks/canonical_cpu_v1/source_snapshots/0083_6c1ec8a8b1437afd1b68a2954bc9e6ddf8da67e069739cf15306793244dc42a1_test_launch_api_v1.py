"""Installed ROS launch command construction only; no launch/service/process runs."""
import argparse
from pathlib import Path
import shlex
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, '/opt/ros/humble/lib/python3.10/site-packages')
from launch import LaunchContext
from launch.descriptions import Executable
from ros2launch.command.launch import LaunchCommand
from ros2launch.api import api
import fixed_integration_v1 as integration


class InstalledLaunchApiTests(unittest.TestCase):
    def test_installed_launch_api_passes_prefix_and_filter_as_launch_configurations(self):
        prefix = '/usr/bin/python3 -B ' + shlex.quote(str(integration.ENTRY))
        service = mock.Mock()
        service.run.return_value = 0
        args = SimpleNamespace(launch_prefix=prefix, launch_prefix_filter='^(motion_safety|mr3_adapter)$')
        with mock.patch.object(api.launch, 'LaunchService', return_value=service) as factory:
            result = api.launch_a_launch_file(launch_file_path='/tmp/artificial_never_loaded.launch.py',
                                               launch_file_arguments=[], args=args)
        self.assertEqual(result, 0)
        self.assertEqual(factory.call_args.kwargs['argv'], [
            'launch-prefix:=' + prefix, 'launch-prefix-filter:=^(motion_safety|mr3_adapter)$'])
        service.include_launch_description.assert_called_once()

    def test_installed_cli_accepts_the_exact_projected_prefix_arguments(self):
        prefix = '/usr/bin/python3 -B ' + shlex.quote(str(integration.ENTRY))
        parser = argparse.ArgumentParser()
        LaunchCommand().add_arguments(parser, 'ros2 launch')
        args = parser.parse_args(['--launch-prefix', prefix, '--launch-prefix-filter',
                                  '^(motion_safety|mr3_adapter)$', 'multi_robot',
                                  'gazebo_multirobot_mapping_with_nav2.launch.py'])
        self.assertEqual(args.launch_prefix, prefix)
        self.assertEqual(args.launch_prefix_filter, '^(motion_safety|mr3_adapter)$')
        self.assertEqual(args.package_name, 'multi_robot')

    def test_installed_executable_prepare_wraps_only_the_two_exact_basenames(self):
        prefix = '/usr/bin/python3 -B ' + shlex.quote(str(integration.ENTRY))
        context = LaunchContext()
        context.launch_configurations['launch-prefix'] = prefix
        context.launch_configurations['launch-prefix-filter'] = '^(motion_safety|mr3_adapter)$'
        root = integration.ROS / 'install/multi_robot_exploration/lib/multi_robot_exploration'
        for basename in ['motion_safety', 'mr3_adapter', 'motion_safety_extra', 'gzserver', 'python3']:
            original = [str(root / basename), '--ros-args', '-r', '__node:=' + basename,
                        '--params-file', '/tmp/actual_launch_params_fixture.yaml']
            executable = Executable(cmd=original)
            executable.prepare(context, None)
            expected = shlex.split(prefix) + original if basename in ('motion_safety', 'mr3_adapter') else original
            self.assertEqual(executable.final_cmd, expected)


if __name__ == '__main__':
    unittest.main()
