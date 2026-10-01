import pytest

from stage_p3b5_return_probe import owned_coordinator


def process(root, pid, parent, domain, coordinator=False):
    directory = root / str(pid)
    directory.mkdir()
    (directory / 'stat').write_text(f'{pid} (python with spaces) S {parent} 0 0')
    (directory / 'cmdline').write_bytes(b'python\0' + (b'__node:=headquarters_control\0' if coordinator else b''))
    (directory / 'environ').write_bytes(f'ROS_DOMAIN_ID={domain}\0'.encode())


def test_fixture_signals_only_the_same_domain_owned_descendant(tmp_path):
    process(tmp_path, 10, 1, 180)
    process(tmp_path, 20, 10, 180)
    process(tmp_path, 30, 20, 180, True)
    process(tmp_path, 40, 1, 180, True)
    process(tmp_path, 50, 10, 181, True)
    assert owned_coordinator(10, '180', tmp_path) == 30
    with pytest.raises(RuntimeError):
        owned_coordinator(99, '180', tmp_path)
    process(tmp_path, 60, 20, 180, True)
    with pytest.raises(RuntimeError):
        owned_coordinator(10, '180', tmp_path)
