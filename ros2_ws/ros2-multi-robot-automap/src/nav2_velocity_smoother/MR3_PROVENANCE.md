# MR3 Nav2 velocity smoother overlay

Upstream: https://github.com/ros-navigation/navigation2/tree/1.1.20/nav2_velocity_smoother
Tag commit: `a097086719c88f781aa59788eca29ac6ca5e56db` (1.1.20).
The upstream Apache 2.0 license and package sources are retained.

MR3 changes only two timer factories in `src/velocity_smoother.cpp` and adds
`rclcpp/create_timer.hpp`: activation and dynamic frequency reconfiguration use
the node clock through `rclcpp::create_timer`. With `use_sim_time=true`, paused
simulation time must not accumulate wall-time OPEN_LOOP velocity increments.
Normal real-time operation uses the same node clock contract.

The constraints algorithm, parameters, topics, lifecycle, dependencies and
executable name remain upstream 1.1.20. This change does not prove physical
velocity or task success; those retain independent native acceptance gates.
