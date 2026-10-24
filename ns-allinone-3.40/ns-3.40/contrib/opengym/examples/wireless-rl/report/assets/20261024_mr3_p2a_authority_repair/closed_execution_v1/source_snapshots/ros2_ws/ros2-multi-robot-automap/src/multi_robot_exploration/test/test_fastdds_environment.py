"""Check the explicit same-host DDS environment without creating participants."""

import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest


ROOT = Path(__file__).resolve().parents[3]
PROFILE = ROOT / 'src/multi_robot/config/mr3_fastdds_loopback_udp.xml'
NS = {'dds': 'http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles'}
ENV_KEYS = (
    'RMW_IMPLEMENTATION', 'ROS_LOCALHOST_ONLY', 'FASTRTPS_DEFAULT_PROFILES_FILE',
    'SKIP_DEFAULT_XML', 'FASTDDS_DEFAULT_PROFILES_FILE', 'RMW_FASTRTPS_USE_QOS_FROM_XML',
    'RMW_FASTRTPS_PUBLICATION_MODE',
)


def load_smoke():
    """Load the CLI without importing ROS or initializing its runtime."""
    spec = importlib.util.spec_from_file_location(
        'smoke_environment', ROOT / 'scripts/ros_smoke_test.py',
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_profile_uses_only_one_default_loopback_udp_transport():
    root = ET.parse(PROFILE).getroot()
    assert root.tag == f"{{{NS['dds']}}}profiles"
    assert [child.tag for child in root] == [
        f"{{{NS['dds']}}}transport_descriptors", f"{{{NS['dds']}}}participant",
    ] + [f"{{{NS['dds']}}}publisher"] * 45
    transports = root.findall('dds:transport_descriptors/dds:transport_descriptor', NS)
    assert len(transports) == 1
    transport = transports[0]
    assert [child.tag for child in transport] == [
        f"{{{NS['dds']}}}transport_id", f"{{{NS['dds']}}}type",
        f"{{{NS['dds']}}}interfaceWhiteList",
    ]
    assert transport.findtext('dds:type', namespaces=NS) == 'UDPv4'
    assert [node.text for node in transport.findall('dds:interfaceWhiteList/dds:address', NS)] == [
        '127.0.0.1',
    ]
    participants = root.findall('dds:participant', NS)
    assert len(participants) == 1
    assert participants[0].get('is_default_profile') == 'true'
    rtps = participants[0].find('dds:rtps', NS)
    assert [child.tag for child in rtps] == [
        f"{{{NS['dds']}}}userTransports", f"{{{NS['dds']}}}useBuiltinTransports",
    ]
    assert rtps.findtext('dds:useBuiltinTransports', namespaces=NS) == 'false'
    assert [node.text for node in rtps.findall('dds:userTransports/dds:transport_id', NS)] == [
        transport.findtext('dds:transport_id', namespaces=NS),
    ]
    # Transport settings contain no non-blocking send, buffer or discovery override.
    assert len(list(root.find('dds:participant', NS).iter())) == 5


def test_only_exact_nav2_lifecycle_replies_get_distinct_bounded_matching_waits():
    root = ET.parse(PROFILE).getroot()
    nodes = ('controller_server', 'planner_server', 'behavior_server',
             'bt_navigator', 'waypoint_follower', 'velocity_smoother')
    expected = {f'rr/tb{robot}/{node}/{service}Reply': seconds
                for robot in range(1, 4) for node in nodes
                for service, seconds in [('change_state', 5), ('get_state', 1)]}
    all_writers = root.findall('dds:publisher', NS)
    writers = [writer for writer in all_writers if writer.attrib['profile_name'] in expected]
    assert len(writers) == 36
    assert {writer.attrib['profile_name'] for writer in writers} == set(expected)
    for writer in writers:
        assert set(writer.attrib) == {'profile_name'}
        assert [child.tag for child in writer] == [f"{{{NS['dds']}}}qos"]
        qos = writer.find('dds:qos', NS)
        assert [child.tag for child in qos] == [f"{{{NS['dds']}}}reliability"]
        reliability = qos.find('dds:reliability', NS)
        assert [child.tag for child in reliability] == [
            f"{{{NS['dds']}}}kind", f"{{{NS['dds']}}}max_blocking_time",
        ]
        assert reliability.findtext('dds:kind', namespaces=NS) == 'RELIABLE'
        duration = reliability.find('dds:max_blocking_time', NS)
        assert [(child.tag, child.text) for child in duration] == [
            (f"{{{NS['dds']}}}sec", str(expected[writer.attrib['profile_name']])),
            (f"{{{NS['dds']}}}nanosec", '0'),
        ]
        assert len(list(writer.iter())) == 7
    # Reader, wildcard and default writers cannot affect contact/control endpoints.
    assert root.findall('dds:subscriber', NS) == []
    assert root.findall('dds:data_reader', NS) == []
    assert root.findall('dds:data_writer', NS) == []
    assert all('*' not in name and name != 'service' for name in expected)


def test_nine_exact_parameter_replies_add_only_bounded_response_matching_waits():
    root = ET.parse(PROFILE).getroot()
    expected = {f'rr/tb{robot}/{node}/get_parametersReply'
                for robot in range(1, 4)
                for node in ('controller_server', 'behavior_server', 'velocity_smoother')}
    all_writers = root.findall('dds:publisher', NS)
    assert len(all_writers) == 45
    names = [writer.attrib['profile_name'] for writer in all_writers]
    assert len(set(names)) == 45
    writers = [writer for writer in all_writers if writer.attrib['profile_name'] in expected]
    assert len(writers) == 9
    assert {writer.attrib['profile_name'] for writer in writers} == expected
    for writer in writers:
        assert set(writer.attrib) == {'profile_name'}
        assert [child.tag for child in writer] == [f"{{{NS['dds']}}}qos"]
        qos = writer.find('dds:qos', NS)
        assert [child.tag for child in qos] == [f"{{{NS['dds']}}}reliability"]
        reliability = qos.find('dds:reliability', NS)
        assert [child.tag for child in reliability] == [
            f"{{{NS['dds']}}}kind", f"{{{NS['dds']}}}max_blocking_time",
        ]
        assert reliability.findtext('dds:kind', namespaces=NS) == 'RELIABLE'
        duration = reliability.find('dds:max_blocking_time', NS)
        assert [(child.tag, child.text) for child in duration] == [
            (f"{{{NS['dds']}}}sec", '1'), (f"{{{NS['dds']}}}nanosec", '0'),
        ]
        assert len(list(writer.iter())) == 7
    assert root.findall('dds:subscriber', NS) == []
    assert root.findall('dds:data_reader', NS) == []
    assert root.findall('dds:data_writer', NS) == []
    assert all(not any(token in name for token in ('*', '?', '[', ']'))
               and name != 'service' for name in names)


def test_p1a_environment_avoids_rmw_localhost_shm_append_and_xml_qos(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.setenv(key, 'ambient_override')
    monkeypatch.setenv('ROS_LOCALHOST_ONLY', '1')
    monkeypatch.setenv('RMW_FASTRTPS_USE_QOS_FROM_XML', '1')
    monkeypatch.setenv('ROS_DOMAIN_ID', '95')
    monkeypatch.setenv('GAZEBO_MASTER_URI', 'http://127.0.0.1:11851')
    monkeypatch.setenv('PYTHONNOUSERSITE', '1')
    smoke = load_smoke()
    metadata = smoke.configure_mr3_transport_environment()
    assert os.environ['RMW_IMPLEMENTATION'] == 'rmw_fastrtps_cpp'
    assert os.environ['ROS_LOCALHOST_ONLY'] == '0'
    assert os.environ['FASTRTPS_DEFAULT_PROFILES_FILE'] == str(PROFILE.resolve())
    assert os.environ['SKIP_DEFAULT_XML'] == '1'
    for key in ('FASTDDS_DEFAULT_PROFILES_FILE', 'RMW_FASTRTPS_USE_QOS_FROM_XML',
                'RMW_FASTRTPS_PUBLICATION_MODE'):
        assert key not in os.environ
        assert metadata[key] is None
    assert metadata['profile_sha256'] == hashlib.sha256(PROFILE.read_bytes()).hexdigest()
    assert os.environ['ROS_DOMAIN_ID'] == '95'
    assert os.environ['GAZEBO_MASTER_URI'] == 'http://127.0.0.1:11851'
    assert os.environ['PYTHONNOUSERSITE'] == '1'


def test_missing_profile_cannot_partially_change_runtime_environment(monkeypatch, tmp_path):
    for key in ENV_KEYS:
        monkeypatch.setenv(key, 'original_value')
    smoke = load_smoke()
    smoke.PROJECT_ROOT = tmp_path
    before = dict(os.environ)
    with pytest.raises(FileNotFoundError):
        smoke.configure_mr3_transport_environment()
    assert dict(os.environ) == before


@pytest.mark.parametrize('contract', [None, {'sha256': 'contract'}])
def test_smoke_selects_transport_before_any_ros_command_only_for_contract(monkeypatch, contract):
    smoke = load_smoke()
    monkeypatch.setattr(smoke, 'parse_args', lambda: object())
    monkeypatch.setattr(smoke, 'resolve_task_settings', lambda *args: contract)
    configured = []
    monkeypatch.setattr(
        smoke, 'configure_mr3_transport_environment', lambda: configured.append(True),
    )

    def check_cli(_name):
        assert configured == ([True] if contract else [])
        return None

    monkeypatch.setattr(smoke.shutil, 'which', check_cli)
    with pytest.raises(SystemExit, match='source /opt/ros/humble/setup.bash'):
        smoke.main()


def test_baseline_binds_and_records_environment_before_running_episode(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location(
        'baseline_environment', ROOT / 'scripts/run_ideal_baseline.py',
    )
    baseline = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / 'scripts'))
    try:
        spec.loader.exec_module(baseline)
    finally:
        sys.path.pop(0)
    monkeypatch.setattr(baseline, 'parse_args', lambda: SimpleNamespace(
        seeds=[101], robot_count=3, world='p1c_rooms.world', duration=300.,
        coverage_threshold=.95, task_contract=ROOT / 'src/multi_robot/config/mr3_p1a/rooms.json',
        goal_timeout=60., startup_timeout=300., message_timeout=90.,
        evaluation_wait_timeout=900., shutdown_timeout=60., run_id='environment',
        output_root=tmp_path,
    ))
    events = []
    metadata = {'profile_sha256': 'declared-profile-hash', 'ROS_LOCALHOST_ONLY': '0'}

    def configure():
        events.append('configure')
        return metadata

    def episode(command, **kwargs):
        assert events == ['configure']
        events.append('episode')
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(baseline, 'configure_mr3_transport_environment', configure)
    monkeypatch.setattr(baseline.subprocess, 'run', episode)
    assert baseline.main() == 1
    import json
    summary = json.loads((tmp_path / 'environment/summary.json').read_text())
    assert summary['transport_environment'] == metadata
    assert events == ['configure', 'episode']


@pytest.mark.parametrize('reason', ['timeout', 'missingserver', 'cli_failure'])
def test_native_stop_error_stays_failure_even_after_clean_exit(reason):
    smoke = load_smoke()
    marker = f'[launch] MR3_GAZEBO_NATIVE_STOP_ERROR reason={reason}'
    log = '\n'.join((
        '[gz-stop-10] process has finished cleanly [pid 100]', marker,
        '[gzserver-4] process has finished cleanly [pid 101]',
    ))
    assert smoke.native_launch_failures(log) == [marker]


def test_native_stop_success_does_not_hide_child_abort():
    smoke = load_smoke()
    clean = '[gzserver-4] process has finished cleanly [pid 101]'
    assert smoke.native_launch_failures(clean) == []
    abort = '[ERROR] [gzserver-4]: process has died [pid 101, exit code -6]'
    assert smoke.native_launch_failures(clean + '\n' + abort) == [abort]


@pytest.mark.parametrize('shutdown_times_out', [False, True])
@pytest.mark.parametrize('failure', ['startup_collision', 'invalid_json', 'validator_error'])
def test_terminal_failure_waits_for_native_stop_before_owned_signal(
    monkeypatch, tmp_path, capsys, shutdown_times_out, failure,
):
    smoke = load_smoke()
    monkeypatch.setenv('ROS_DISTRO', 'humble')
    monkeypatch.setattr(smoke.shutil, 'which', lambda _name: '/usr/bin/ros2')
    monkeypatch.setattr(smoke, 'parse_args', lambda: SimpleNamespace(
        robot_count=3, world='p1c_rooms.world', gazebo_seed=101, goal_timeout=60.,
        spawn_timeout=90., startup_timeout=300., message_timeout=90.,
        dwell_seconds=0., shutdown_timeout=60., evaluation_duration=180.,
        coverage_threshold=.9, evaluation_wait_timeout=900., episode_id='terminal',
        task_contract=None, evaluation_output_dir=tmp_path / 'evaluation',
        log_dir=tmp_path / 'logs',
    ))
    monkeypatch.setattr(smoke, 'run_ros', lambda *args, **kwargs: (
        subprocess.CompletedProcess([], 0, '', '')
    ))
    events = []
    process = SimpleNamespace(returncode=None, poll=lambda: process.returncode)

    def launch(*args, **kwargs):
        events.append('launch')
        result = tmp_path / 'evaluation/terminal.json'
        result.parent.mkdir()
        result.write_text('{}')
        return process

    def terminal_result(*args, **kwargs):
        raise RuntimeError('native terminal=' + failure)

    def wait(timeout):
        events.append(('wait', timeout))
        if shutdown_times_out:
            raise subprocess.TimeoutExpired('owned_launch', timeout)
        process.returncode = 0

    def stop(_process, timeout):
        events.append(('cleanup', timeout, process.poll()))
        process.returncode = 0
        return True

    process.wait = wait
    monkeypatch.setattr(smoke.subprocess, 'Popen', launch)
    monkeypatch.setattr(smoke, 'wait_until_ready', lambda *args, **kwargs: False)
    monkeypatch.setattr(smoke, 'wait_for_evaluation', terminal_result)
    monkeypatch.setattr(smoke, 'stop_launch', stop)
    assert smoke.main() == 1
    assert events == [
        'launch', ('wait', 60.),
        ('cleanup', 0 if shutdown_times_out else 60., None if shutdown_times_out else 0),
    ]
    error = capsys.readouterr().err
    assert 'native terminal=' + failure in error
    assert ('owned launch did not shut down' in error) is shutdown_times_out


def test_real_probe_error_without_terminal_json_keeps_immediate_owned_cleanup(
    monkeypatch, tmp_path, capsys,
):
    smoke = load_smoke()
    monkeypatch.setenv('ROS_DISTRO', 'humble')
    monkeypatch.setattr(smoke.shutil, 'which', lambda _name: '/usr/bin/ros2')
    monkeypatch.setattr(smoke, 'parse_args', lambda: SimpleNamespace(
        robot_count=3, world='p1c_rooms.world', gazebo_seed=101, goal_timeout=60.,
        spawn_timeout=90., startup_timeout=300., message_timeout=90.,
        dwell_seconds=0., shutdown_timeout=60., evaluation_duration=180.,
        coverage_threshold=.9, evaluation_wait_timeout=900., episode_id='probe',
        task_contract=None, evaluation_output_dir=tmp_path / 'evaluation',
        log_dir=tmp_path / 'logs',
    ))
    monkeypatch.setattr(smoke, 'run_ros', lambda *args, **kwargs: (
        subprocess.CompletedProcess([], 0, '', '')
    ))
    events = []
    process = SimpleNamespace(returncode=None, poll=lambda: process.returncode)
    process.wait = lambda **kwargs: pytest.fail('must not wait without terminal JSON')
    monkeypatch.setattr(smoke.subprocess, 'Popen', lambda *args, **kwargs: process)
    monkeypatch.setattr(smoke, 'wait_until_ready', lambda *args, **kwargs: True)

    def probe(*args, **kwargs):
        raise TimeoutError('genuine probe timeout')

    def stop(_process, timeout):
        events.append(timeout)
        process.returncode = 0
        return True

    monkeypatch.setattr(smoke, 'require_message', probe)
    monkeypatch.setattr(smoke, 'stop_launch', stop)
    assert smoke.main() == 1
    assert events == [60.]
    assert 'genuine probe timeout' in capsys.readouterr().err
