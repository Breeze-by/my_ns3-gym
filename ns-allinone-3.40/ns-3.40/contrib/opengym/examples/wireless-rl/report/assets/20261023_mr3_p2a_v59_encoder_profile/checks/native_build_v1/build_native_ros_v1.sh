#!/bin/bash
set -eo pipefail
unset PYTHONPATH
unset LD_LIBRARY_PATH
export PATH=/usr/bin:/bin
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES=""
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
/usr/bin/python3 /usr/bin/colcon build --packages-select multi_robot --symlink-install --allow-overriding nav2_bringup nav2_velocity_smoother --event-handlers console_direct+ --cmake-args -DCMAKE_VERBOSE_MAKEFILE=ON -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=/usr/bin/python3
