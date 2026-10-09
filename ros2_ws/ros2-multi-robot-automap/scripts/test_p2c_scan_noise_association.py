"""Native C++ masks, raw source counterexamples and independent reconstruction."""
import base64
import json
import math
from pathlib import Path
import subprocess

import numpy as np
import pytest
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import LaserScan

from p2c_scan_self_filter import (PROJECT, body_return_mask, noise_associated_mask,
                                 physical_body_box, physical_range_uncertainty)

BOX = physical_body_box()
LASER = [-.064, 0., 0.]


@pytest.fixture(scope='module')
def cpp_mask(tmp_path_factory):
    root = tmp_path_factory.mktemp('scan_noise_cpp')
    source = root/'probe.cpp'
    source.write_text('''#include <iostream>
#include <string>
#include "slam_toolbox/scan_self_filter.hpp"
int main() {
  std::string token;
  while (std::cin >> token) {
    const int count = std::stoi(token);
    double p[12];
    for (double & v : p) {if (!(std::cin >> token)) return 2; v=std::stod(token);}
    std::vector<float> ranges;
    for (int i=0; i<count; ++i) {
      if (!(std::cin >> token)) return 2;
      ranges.push_back(static_cast<float>(std::stod(token)));
    }
    const auto mask=slam_toolbox::scan_self_filter::selfReturnMask(ranges,
      p[0],p[1],p[2],p[3],p[4],p[5],p[6],{p[7],p[8],p[9],p[10]},p[11]);
    for (bool v : mask) std::cout << v;
    std::cout << '\\n';
  }
}
''')
    binary=root/'probe'
    subprocess.run(['g++','-std=c++14','-Wall','-Wextra','-Werror','-I',
        str(PROJECT/'src/slam_toolbox/include'),str(source),'-o',str(binary)],check=True)

    def run(scan, uncertainty=.0375, laser=LASER):
        values=[len(scan.ranges),scan.angle_min,scan.angle_increment,scan.range_min,scan.range_max,
                *laser,*BOX,uncertainty,*scan.ranges]
        result=subprocess.run([str(binary)],input=' '.join(format(v,'.17g') for v in values)+'\n',
            capture_output=True,text=True,check=True)
        return np.array([v=='1' for v in result.stdout.strip()])
    return run


def scan_with(deltas, angle=.95, increment=.01):
    scan=LaserScan();scan.angle_min=angle;scan.angle_increment=increment
    scan.range_min=.12;scan.range_max=10.
    angles=scan.angle_min+np.arange(len(deltas))*scan.angle_increment
    # This synthetic sector crosses the upper rectangle surface.
    with np.errstate(divide='ignore',invalid='ignore'):
        surface=BOX[3]/np.sin(angles)
    scan.ranges=np.asarray(surface+np.array(deltas),dtype=np.float32).tolist()
    return scan


@pytest.mark.parametrize('deltas,expected',[
    ([.01]*9,[]),  # A real nearby obstacle without interior seeds remains.
    ([.01,.01,.01,.01,-.008,.01,.01,.01,.01],list(range(9))),
    ([.01,-.008],[1]),  # Two beams cannot support boundary-noise association.
    ([.01,.01,.01,-.008,-.008,.01,.01,.01,.01],list(range(9))),
    ([.01,.01,.01,-.008,-.008,1.,.01,.01,.01],list(range(5))),
    ([.05,.01,.01,-.008,-.008,.01,.01,.01,.05],list(range(1,8))),
])
def test_seeded_cluster_and_nearby_external_counterexamples(cpp_mask,deltas,expected):
    scan=scan_with(deltas)
    assert np.flatnonzero(cpp_mask(scan)).tolist()==expected
    assert np.flatnonzero(noise_associated_mask(scan,BOX,LASER,.0375)).tolist()==expected


@pytest.mark.parametrize('uncertainty',[0.,-1.,math.nan,math.inf])
def test_disabled_or_invalid_band_keeps_original_strict_mask(cpp_mask,uncertainty):
    scan=scan_with([.01,.01,-.008,-.008,.01])
    assert np.array_equal(cpp_mask(scan,uncertainty),body_return_mask(scan,BOX,LASER))
    assert np.array_equal(noise_associated_mask(scan,BOX,LASER,uncertainty),body_return_mask(scan,BOX,LASER))


@pytest.mark.parametrize('bad',[math.nan,math.inf,.12,10.])
def test_invalid_beam_breaks_association_instead_of_becoming_free(cpp_mask,bad):
    scan=scan_with([.01,.01,.01,-.008,-.008,.01,.01,.01,.01]);scan.ranges[5]=bad
    expected=[0,1,2,3,4]
    assert np.flatnonzero(cpp_mask(scan)).tolist()==expected
    assert np.flatnonzero(noise_associated_mask(scan,BOX,LASER,.0375)).tolist()==expected


def test_external_laser_mount_cannot_extend_body_mask(cpp_mask):
    scan=scan_with([.01,.01,-.008,-.008,.01]);outside=[.3,0.,0.]
    assert not cpp_mask(scan,laser=outside).any()
    assert not noise_associated_mask(scan,BOX,outside,.0375).any()


def test_full_turn_boundary_wrap_has_distinct_seeds_but_partial_scan_does_not(cpp_mask):
    scan=LaserScan();scan.angle_min=0.;scan.angle_increment=2*math.pi/360
    scan.range_min=.12;scan.range_max=10.;scan.ranges=[2.]*360
    scan.ranges[0]=.148;scan.ranges[1]=.124;scan.ranges[359]=.124
    assert np.flatnonzero(cpp_mask(scan)).tolist()==[0,1,359]
    assert np.array_equal(cpp_mask(scan),noise_associated_mask(scan,BOX,LASER,.0375))
    scan.ranges=scan.ranges[:8]
    assert np.flatnonzero(cpp_mask(scan)).tolist()==[1]


def test_original_doorway_scan_contains_associated_boundary_returns(cpp_mask):
    fixture=json.loads((PROJECT/'src/multi_robot_exploration/test/fixtures/p2c_v45_boundary_scan.json').read_text())
    assert fixture['source_commit']=='531b2abde913f162514570bf99955a7ba0b50e85'
    scan=deserialize_message(base64.b64decode(fixture['record']['cdr']),LaserScan)
    old=body_return_mask(scan,BOX,LASER);new=cpp_mask(scan)
    assert np.array_equal(new,noise_associated_mask(scan,BOX,LASER,.0375))
    assert new[61] and new[62] and not old[61] and not old[62]
    assert np.all(new[old]) and new.sum()>old.sum()
    # Original model, raw input header/ranges and body rectangle are unchanged.
    assert physical_range_uncertainty()==.0375


def test_random_float32_scans_and_mounts_match_independent_reader(cpp_mask):
    rng=np.random.default_rng(3917)
    for count,angle,increment in [(360,0.,2*math.pi/360),(23,.1,.03),(15,-1.,-.02)]:
        for _ in range(8):
            scan=scan_with(rng.normal(0,.025,count),angle,increment)
            assert np.array_equal(cpp_mask(scan),noise_associated_mask(scan,BOX,LASER,.0375))
