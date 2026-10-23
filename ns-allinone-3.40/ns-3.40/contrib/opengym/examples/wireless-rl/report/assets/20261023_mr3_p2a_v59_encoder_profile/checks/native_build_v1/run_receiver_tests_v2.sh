#!/bin/bash
set -eo pipefail
unset PYTHONPATH
unset LD_LIBRARY_PATH
export PATH=/usr/bin:/bin
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES=""
source /opt/ros/humble/setup.bash
/usr/bin/ctest --test-dir /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/build/multi_robot --output-on-failure -R '^test_initial_zero_encoder_servo$'
