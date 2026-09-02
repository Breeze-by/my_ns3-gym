# Multi-Robot Task-Oriented Wi-Fi RL

This monorepo combines ns-3/ns3-gym reinforcement learning with a ROS 2
multi-robot mapping and navigation task.

## Repository layout

```text
ns-allinone-3.40/ns-3.40/
  ns-3.40, ns3-gym, and the current wireless-rl experiments

ros2_ws/ros2-multi-robot-automap/
  ROS 2 Humble + Gazebo multi-robot SLAM, exploration, and navigation
```

The long-term goal is to study task-oriented Wi-Fi 4 communication for 2–3
robots that collaboratively map an unknown environment, search for an object,
return to charge when necessary, and rendezvous at the detected object.

Start with the
[`RESEARCH_PLAN.md`](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/RESEARCH_PLAN.md),
then read the component guides:

- [`wireless-rl/USER_GUIDE.md`](ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/USER_GUIDE.md)
- [`ros2-multi-robot-automap/user_guide.md`](ros2_ws/ros2-multi-robot-automap/user_guide.md)

Generated ns-3 outputs, checkpoints, ROS build/install/log directories, maps,
bags, and local environments are intentionally not versioned.

