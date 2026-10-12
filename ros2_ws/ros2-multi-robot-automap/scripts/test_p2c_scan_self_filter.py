import base64
import copy
import gzip
import json
import math
from pathlib import Path
import subprocess

import numpy as np
import pytest
from rclpy.serialization import deserialize_message, serialize_message
from sensor_msgs.msg import LaserScan
from tf2_msgs.msg import TFMessage
from geometry_msgs.msg import TransformStamped

from p2c_scan_self_filter import PROJECT, body_return_mask, physical_body_box, scan_self_filter_audit, noise_associated_mask
from run_p2d_baseline import file_digest

FIXTURE = PROJECT/'src/multi_robot_exploration/test/fixtures/p2c_v43_self_return_scan.json'
BOX = [-.1965, .0685, -.1325, .1325]
LASER = [-.064, 0., 0.]


@pytest.fixture(scope='module')
def cpp_filter(tmp_path_factory):
    directory = tmp_path_factory.mktemp('native_scan_filter_cpp')
    source = directory/'probe.cpp'
    source.write_text('''#include <iostream>
#include <string>
#include "slam_toolbox/scan_self_filter.hpp"
int main() {
  std::string tokens[11];
  while (std::cin >> tokens[0]) {
    for (int i=1; i<11; ++i) if (!(std::cin >> tokens[i])) return 2;
    double v[11];
    for (int i=0; i<11; ++i) v[i]=std::stod(tokens[i]);
    const std::vector<double> box{v[7],v[8],v[9],v[10]};
    std::cout << (v[0]>v[5] && v[0]<v[6] &&
      slam_toolbox::scan_self_filter::insideBody(v[0],v[1],v[2],v[3],v[4],box)) << '\\n';
  }
}
''')
    binary = directory/'probe'
    subprocess.run(['g++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-I',
                    str(PROJECT/'src/slam_toolbox/include'), str(source), '-o', str(binary)], check=True)

    def run(rows):
        text = '\n'.join(' '.join(format(x, '.17g') for x in row) for row in rows)+'\n'
        output = subprocess.run([str(binary)], input=text, text=True, capture_output=True, check=True)
        return [int(x) for x in output.stdout.splitlines()]
    return run


def test_original_physical_geometry_is_the_only_mask():
    assert np.allclose(physical_body_box(), BOX, atol=1e-15, rtol=0)
    assert BOX[0] < LASER[0] < BOX[1]


@pytest.mark.parametrize('range,angle,expected', [
    (.121, 0., 1), (.12, 0., 0), (.14, 0., 0), (.2, math.pi/2, 0),
    (1.1, 0., 0), (10., 0., 0), (-.1, 0., 0), (math.nan, 0., 0),
    (math.inf, 0., 0), (.121, math.nan, 0), (.121, math.inf, 0),
    (.1325, 0., 0), (.1325, math.pi, 0),
])
def test_valid_body_returns_and_external_obstacles(cpp_filter, range, angle, expected):
    assert cpp_filter([[range, angle, *LASER, .12, 10., *BOX]]) == [expected]


def test_translated_rotated_laser_and_box_boundaries(cpp_filter):
    # Every box edge and point outside is retained, even if close to the sensor.
    points = [(BOX[0], 0.), (BOX[1], 0.), (0., BOX[2]), (0., BOX[3]),
              (BOX[1]+1e-6, 0.), (0., BOX[3]+1e-6)]
    rows = []
    for x, y in points:
        rows.append([math.hypot(x, y), math.atan2(y, x)-math.pi/2,
                     0., 0., math.pi/2, 0., 10., *BOX])
    assert cpp_filter(rows) == [0]*len(rows)


def test_original_loss_scan_cpp_keeps_every_external_return(cpp_filter):
    fixture = json.loads(FIXTURE.read_text())
    msg = deserialize_message(base64.b64decode(fixture['record']['cdr']), LaserScan)
    rows = [[range, msg.angle_min+i*msg.angle_increment, *LASER, msg.range_min, msg.range_max, *BOX]
            for i, range in enumerate(msg.ranges)]
    mask = np.asarray(cpp_filter(rows), dtype=bool)
    assert np.flatnonzero(mask).tolist() == fixture['physical_body_interior_beams']
    assert np.array_equal(mask, body_return_mask(msg, BOX, LASER))
    assert len(msg.ranges) == 360 and int(mask.sum()) == 10


@pytest.fixture(scope='module')
def source_digests():
    return {name:file_digest(PROJECT/path) for name,path in (
        ('slam','src/slam_toolbox'),('robot_models','src/multi_robot/models'),
        ('robot_description','src/multi_robot/urdf'),('scan_self_filter_reader','scripts/p2c_scan_self_filter.py'))}


@pytest.mark.parametrize('tamper', [None, 'removed', 'source_time', 'frame', 'source',
                                   'box', 'tf', 'configuration', 'missing_configuration', 'malformed'])
def test_independent_native_original_cdr_witness(tmp_path, source_digests, tamper):
    fixture = json.loads(FIXTURE.read_text());record = fixture['record']
    record = dict(record, topic='/tb1/scan')
    declaration = dict(body_box_m=BOX.copy(),laser_to_base_xy_yaw=LASER.copy(),laser_frame='base_scan',range_uncertainty_m=.0375)
    row = dict(config=dict(native_scan_self_filter=declaration,navigation_input_capture=True),
               result=dict(robot_count=1),source_digests=copy.deepcopy(source_digests))
    static = TFMessage()
    for parent, child, x in [('base_footprint','base_link',0.),('base_link','base_scan',-.064)]:
        t = TransformStamped();t.header.frame_id=parent;t.child_frame_id=child
        t.transform.translation.x=x;t.transform.rotation.w=1.;static.transforms.append(t)
    count = int(noise_associated_mask(deserialize_message(base64.b64decode(record['cdr']), LaserScan), BOX, LASER, .0375).sum())
    config = '[tb1.slam_toolbox]: SCAN_SELF_FILTER_CONFIG box=-0.196500000,0.068500000,-0.132500000,0.132500000 uncertainty=0.037500000\n'
    witness = f'[tb1.slam_toolbox]: SCAN_SELF_FILTER source=2235.173000000 frame=base_scan removed={count}\n'
    if tamper=='removed':witness=witness.replace(f'removed={count}',f'removed={count+1}')
    if tamper=='source_time':witness=witness.replace('2235.173','2235.174')
    if tamper=='frame':witness=witness.replace('frame=base_scan','frame=other')
    if tamper=='source':row['source_digests']['slam']='unbound'
    if tamper=='box':declaration['body_box_m'][1]=.1
    if tamper=='tf':static.transforms[-1].transform.translation.x=-.05
    if tamper=='configuration':config=config.replace('0.068500000','0.100000000')
    if tamper=='missing_configuration':config=''
    if tamper=='malformed':witness=witness.replace(f'removed={count}','removed=oops')
    with gzip.open(tmp_path/'navigation_inputs.jsonl.gz','xt') as stream:
        stream.write(json.dumps(record)+'\n')
        stream.write(json.dumps(dict(topic='/tb1/tf_static',cdr=base64.b64encode(serialize_message(static)).decode()))+'\n')
    (tmp_path/'launch').mkdir();(tmp_path/'launch/native.log').write_text(config+witness)
    if tamper is None:
        result=scan_self_filter_audit(row,tmp_path)
        assert result['native_witnesses']==1 and result['rejected_body_returns']==count
    else:
        with pytest.raises(AssertionError):scan_self_filter_audit(row,tmp_path)
