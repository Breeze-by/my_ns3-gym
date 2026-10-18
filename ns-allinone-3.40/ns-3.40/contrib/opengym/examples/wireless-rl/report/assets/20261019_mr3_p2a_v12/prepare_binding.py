"""Generate the reviewable V12 native file binding before source freeze."""
import hashlib
import json
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".git").exists())
HERE = Path(__file__).resolve().parent
W = HERE.parents[2]
R = ROOT / "ros2_ws/ros2-multi-robot-automap"
S = R / "src/multi_robot"


def source(p):
    p = Path(p)
    return {"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def elf(p):
    p = Path(p)
    raw = p.read_bytes()
    assert raw[:4] == b"\x7fELF"
    return {"path": str(p), "resolved_path": str(p.resolve()),
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def main():
    roles = {
        "gzserver_executable": "/usr/bin/gzserver",
        "driver": R / "install/multi_robot/lib/libmr3_gazebo_diff_drive.so",
        "observer": R / "install/multi_robot/lib/libmr3_stop_response_observer.so",
        "ray_box": R / "install/multi_robot/lib/libmr3_ray_box_corrector.so",
        "ode": "/lib/x86_64-linux-gnu/libgazebo_ode.so.11",
        "smoother_core": R / "install/nav2_velocity_smoother/lib/libvelocity_smoother_core.so",
        "smoother_executable": R / "install/nav2_velocity_smoother/lib/nav2_velocity_smoother/velocity_smoother",
        "odometry_recorder_executable": R / "install/multi_robot/lib/multi_robot/mr3_odometry_recorder",
        "controller_executable": "/opt/ros/humble/lib/nav2_controller/controller_server",
        "rotation_shim": "/opt/ros/humble/lib/libnav2_rotation_shim_controller.so",
    }
    compiled = {
        "driver": {"compiled_source_sha256": "src/mr3_gazebo_diff_drive.cpp",
                   "compiled_header_sha256": "include/multi_robot/mr3_gazebo_diff_drive.hpp",
                   "compiled_helper_sha256": "include/multi_robot/paired_wheel_slew.hpp",
                   "compiled_target_contract_sha256": "include/multi_robot/mr3_drive_target.hpp",
                   "compiled_odometry_json_sha256": "include/multi_robot/mr3_odometry_json.hpp"},
        "observer": {"compiled_source_sha256": "src/mr3_stop_response_observer.cpp"},
        "ray_box": {"compiled_source_sha256": "src/mr3_ray_box_corrector.cpp",
                    "compiled_collision_source_sha256": "src/mr3_ray_box_collision.cpp",
                    "compiled_collision_header_sha256": "include/multi_robot/mr3_ray_box_collision.hpp"},
        "recorder": {"compiled_source_sha256": "src/mr3_odometry_recorder.cpp",
                     "compiled_odometry_json_sha256": "include/multi_robot/mr3_odometry_json.hpp"},
    }
    paths = [R / ("src/nav2_velocity_smoother/" + p) for p in (
        "src/velocity_smoother.cpp", "include/nav2_velocity_smoother/velocity_smoother.hpp",
        "test/test_velocity_smoother.cpp")]
    paths += [S / p for p in ("CMakeLists.txt", "package.xml", "models/turtlebot3_waffle/model.sdf",
                              "launch/gazebo_multirobot_mapping_with_nav2.launch.py")]
    paths += [S / f"params/nav2_params_tb{i}_0.yaml" for i in (1, 2, 3)]
    paths += [R / "scripts/mr3_env_worker.py", W / "mr3_learning/native_custody.py"]
    paths += [W / "report/assets/20261019_mr3_p2a_v8/checks/mr3_smoother_diagnostic_tests_installed_v2.xml"]
    result = {"schema": "mr3-native-custody-binding-v1", "optional_observer_per_episode": True,
              "binaries": {k: (dict(elf(v), stat={"dev": Path(v).stat().st_dev, "ino": Path(v).stat().st_ino})
                                if k == "gzserver_executable" else elf(v)) for k, v in roles.items()},
              "compiled_sources": {role: {k: source(S / v) for k, v in fields.items()}
                                   for role, fields in compiled.items()},
              "source_bindings": [source(p) for p in paths],
              "build_receipts": [source(W / "report/assets/20261019_mr3_p2a_v12/checks/v12_build.json"),
                                 source(W / "report/assets/20261019_mr3_p2a_v8/checks/mr3_smoother_diagnostic_installed_cpu_v2.json")],
              "process_tools": source(W / "report/assets/20261017_mr3_p2a0_v13/independent/mr3_readonly_v13_drive_shim_process_monitor_v2.py"),
              "corrector_tools": source(W / "report/assets/20261018_mr3_p2a0_v24_install/independent/mr3_v24_corrector_custody_v3.py"),
              "corrector_binding": source(W / "report/assets/20261018_mr3_p2a0_v24_install/independent/mr3_v24_corrector_binding_v1.json")}
    (HERE / "native_custody_binding.json").write_text(json.dumps(result, indent=2) + "\n")
    print("V12 binding generated; review and freeze before native use")


if __name__ == "__main__":
    main()
