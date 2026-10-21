// Fixed artificial calls to the existing SDK occupancy kernel; no ROS node,
// World, Mapper, real scene, scan matching, actor or task-quality claim.
#include <karto_sdk/Karto.h>
#include <unistd.h>
#include <cmath>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using Vec = karto::Vector2<kt_double>;
using Index = karto::Vector2<kt_int32s>;
std::vector<std::string> errors, results;

std::string quote(const std::string &value) {
  std::ostringstream out; out << '"';
  for (unsigned char c : value) {
    if (c == '"' || c == '\\') out << '\\' << c;
    else if (c < 32) out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << unsigned(c) << std::dec;
    else out << c;
  }
  return out.str() + '"';
}
void check(bool ok, const std::string &message) { if (!ok) errors.push_back(message); }
bool close(double a, double b) { return std::abs(a - b) <= 1e-12; }
int ros_value(unsigned value) {
  switch (value) {
    case karto::GridStates_Unknown: return -1;
    case karto::GridStates_Occupied: return 100;
    case karto::GridStates_Free: return 0;
    default: throw std::runtime_error("unexpected SDK grid state");
  }
}
struct FixedGrid : karto::OccupancyGrid {
  FixedGrid(int width = 24, int height = 4, double resolution = 1.)
  : karto::OccupancyGrid(width, height, Vec(0., 0.), resolution) {
    // The public constructor leaves the two counter grids at 0x0.
    karto::LocalizedRangeScanVector empty;
    karto::OccupancyGrid::CreateFromScans(empty);
  }
  using karto::OccupancyGrid::AddScan;
  using karto::OccupancyGrid::RayTrace;
  using karto::OccupancyGrid::Update;
  using karto::OccupancyGrid::GetCellPassCounts;
  using karto::OccupancyGrid::GetCellHitsCounts;
  unsigned pass(int x, int y) { return GetCellPassCounts()->GetValue(Index(x, y)); }
  unsigned hit(int x, int y) { return GetCellHitsCounts()->GetValue(Index(x, y)); }
  unsigned state(int x, int y) { return GetValue(Index(x, y)); }
  std::string cell(int x, int y) {
    std::ostringstream out;
    out << "{\"x\":" << x << ",\"y\":" << y << ",\"pass\":" << pass(x,y)
        << ",\"hit\":" << hit(x,y) << ",\"sdk_state\":" << state(x,y)
        << ",\"map_state\":" << ros_value(state(x,y)) << '}';
    return out.str();
  }
};
struct Sensor {
  std::unique_ptr<karto::LaserRangeFinder> laser;
  std::string name;
  bool registered = false;
  Sensor(const std::string &label, unsigned beams, double threshold = 10.) : name(label) {
    laser.reset(karto::LaserRangeFinder::CreateLaserRangeFinder(karto::LaserRangeFinder_Custom, karto::Name(name)));
    laser->SetMinimumRange(.12); laser->SetMaximumRange(10.); laser->SetRangeThreshold(threshold);
    laser->SetMinimumAngle(beams == 1 ? 0. : -.1);
    laser->SetMaximumAngle(beams == 1 ? 0. : .1);
    laser->SetAngularResolution(.1); laser->SetIs360Laser(false);
    karto::SensorManager::GetInstance()->RegisterSensor(laser.get()); registered = true;
  }
  ~Sensor() {
    if (registered) {
      try { karto::SensorManager::GetInstance()->UnregisterSensor(laser.get()); }
      catch (...) { errors.push_back(name + ": sensor unregister failed"); }
    }
  }
};
void pose(karto::LocalizedRangeScan &scan, const karto::Pose2 &estimated) {
  scan.SetOdometricPose(estimated); scan.SetCorrectedPose(estimated);
}
void run_case(const std::string &name, const std::function<std::string()> &body) {
  const auto before = errors.size(); std::string data = "{}";
  try { data = body(); }
  catch (const karto::Exception &error) { errors.push_back(name + ": SDK " + error.GetErrorMessage()); }
  catch (const std::exception &error) { errors.push_back(name + ": " + error.what()); }
  catch (...) { errors.push_back(name + ": unknown exception"); }
  results.push_back("{\"id\":" + quote(name) + ",\"checks_passed\":" +
                    (errors.size() == before ? "true" : "false") + ",\"actual\":" + data + '}');
}

int main() {
  // SensorManager writes registration messages to cout; preserve them without
  // mixing non-JSON lines into the machine-readable stdout protocol.
  std::ostringstream sdk_log; auto *stdout_buffer = std::cout.rdbuf(sdk_log.rdbuf());
  run_case("round_padding_and_state_mapping", [] {
    FixedGrid grid(5, 4); std::ostringstream out;
    out << "{\"width\":5,\"height\":4,\"width_step\":" << grid.GetWidthStep() << ",\"round_indices\":[";
    const double values[] = {.5, -.5, 1.5, -1.5}; const int expected[] = {1, -1, 2, -2};
    for (int i = 0; i < 4; ++i) {
      auto index = grid.WorldToGrid(Vec(values[i], values[i]));
      check(index.GetX() == expected[i] && index.GetY() == expected[i], "Round is not half-away-from-zero");
      if (i) out << ','; out << index.GetX();
    }
    check(grid.GetWidthStep() == 8, "SDK row padding was not preserved");
    check(ros_value(0) == -1 && ros_value(100) == 100 && ros_value(255) == 0, "state mapping mismatch");
    out << "],\"state_mapping\":[[0,-1],[100,100],[255,0]],\"initial_cell\":" << grid.cell(4,3) << '}';
    return out.str();
  });
  run_case("per_beam_counts_and_strict_min_pass", [] {
    FixedGrid grid; std::ostringstream out;
    check(grid.RayTrace(Vec(.1,.1), Vec(3.1,.1), true), "valid hit ray endpoint outside grid"); grid.Update();
    check(grid.pass(3,0) == 2 && grid.hit(3,0) == 1 && grid.state(3,0) == 0, "first hit must be pass2/hit1/unknown");
    out << "{\"first_hit\":" << grid.cell(3,0);
    grid.RayTrace(Vec(.1,.1), Vec(3.1,.1), true); grid.Update();
    check(grid.pass(3,0) == 4 && grid.hit(3,0) == 2 && grid.state(3,0) == 100, "second identical hit must accumulate");
    check(grid.pass(1,0) == 2 && grid.state(1,0) == 0, "pass==2 must still be unknown");
    out << ",\"second_hit\":" << grid.cell(3,0) << ",\"interior_after_two\":" << grid.cell(1,0);
    grid.RayTrace(Vec(.1,.1), Vec(3.1,.1), false); grid.Update();
    check(grid.pass(3,0) == 5 && grid.hit(3,0) == 2, "nohit must add one pass, no hit");
    check(grid.pass(1,0) == 3 && grid.hit(1,0) == 0 && grid.state(1,0) == 255, "ordinary free requires pass>2");
    out << ",\"after_nohit_endpoint\":" << grid.cell(3,0) << ",\"ordinary_free\":" << grid.cell(1,0) << '}';
    return out.str();
  });
  run_case("native_min_max_skip_vs_explicit_max_nohit", [] {
    Sensor sensor("cpu_min_max", 1); FixedGrid native, kernel; bool validated = true;
    for (double range : {.12, 10.}) {
      karto::LocalizedRangeScan scan(karto::Name(sensor.name), karto::RangeReadingsVector{range});
      pose(scan, karto::Pose2(.1,.1,0.)); validated &= sensor.laser->Validate(&scan);
      if (sensor.laser->Validate(&scan)) native.AddScan(&scan);
    }
    native.Update();
    for (int i = 0; i < 3; ++i) kernel.RayTrace(Vec(.1,.1), Vec(10.1,.1), false);
    kernel.Update();
    check(validated && native.pass(0,0) == 0 && native.pass(10,0) == 0, "native AddScan must ignore range==min/max");
    check(kernel.pass(10,0) == 3 && kernel.hit(10,0) == 0 && kernel.state(10,0) == 255, "explicit kernel max-nohit differs from native ingress");
    return "{\"native_validated\":" + std::string(validated ? "true" : "false") +
      ",\"native_start\":" + native.cell(0,0) + ",\"native_max_endpoint\":" + native.cell(10,0) +
      ",\"explicit_max_nohit_endpoint\":" + kernel.cell(10,0) + '}';
  });
  run_case("native_threshold_clipping_and_tolerance", [] {
    Sensor sensor("cpu_threshold", 1, 2.); FixedGrid clipped, tolerance;
    for (int i = 0; i < 3; ++i) {
      karto::LocalizedRangeScan scan(karto::Name(sensor.name), karto::RangeReadingsVector{3.});
      pose(scan, karto::Pose2(.1,.1,0.));
      const bool valid = sensor.laser->Validate(&scan);
      check(valid, "threshold scan validation failed"); if (valid) clipped.AddScan(&scan);
    }
    karto::LocalizedRangeScan near(karto::Name(sensor.name), karto::RangeReadingsVector{2. - .5e-6});
    pose(near, karto::Pose2(.1,.1,0.));
    const bool valid = sensor.laser->Validate(&near);
    check(valid, "near-threshold scan validation failed"); if (valid) tolerance.AddScan(&near);
    clipped.Update(); tolerance.Update();
    check(clipped.pass(2,0) == 3 && clipped.hit(2,0) == 0 && clipped.pass(3,0) == 0, "native threshold must clip ray without a hit");
    check(tolerance.pass(2,0) == 1 && tolerance.hit(2,0) == 0, "native threshold-1e-6 endpoint-valid tolerance changed");
    return "{\"range_threshold\":2,\"input_range\":3,\"clipped_endpoint\":" + clipped.cell(2,0) +
      ",\"beyond_threshold\":" + clipped.cell(3,0) + ",\"near_threshold_nohit\":" + tolerance.cell(2,0) + '}';
  });
  run_case("native_same_scan_object_is_not_idempotent", [] {
    Sensor sensor("cpu_repeated_scan", 1); FixedGrid grid;
    karto::LocalizedRangeScan scan(karto::Name(sensor.name), karto::RangeReadingsVector{1.1});
    pose(scan, karto::Pose2(.1,.1,0.)); const bool valid = sensor.laser->Validate(&scan);
    check(valid, "repeated scan validation failed");
    if (valid) grid.AddScan(&scan); grid.Update(); const auto first = grid.cell(1,0);
    if (valid) grid.AddScan(&scan); grid.Update();
    check(grid.pass(1,0) == 4 && grid.hit(1,0) == 2, "same scan object must count its beams twice");
    return "{\"same_scan_object\":true,\"addscan_calls\":2,\"first\":" + first +
      ",\"second\":" + grid.cell(1,0) + '}';
  });
  run_case("estimated_pose_sensor_offset_once_and_validated_count", [] {
    Sensor sensor("cpu_offset", 3); sensor.laser->SetOffsetPose(karto::Pose2(-.064, 0., .2));
    karto::LocalizedRangeScan scan(karto::Name(sensor.name), karto::RangeReadingsVector{.5,.5,.5});
    const double yaw = std::acos(-1.) / 2.; pose(scan, karto::Pose2(2.,3.,yaw));
    const bool valid = sensor.laser->Validate(&scan); check(valid, "three-beam scan validation failed");
    const auto actual = scan.GetSensorPose();
    check(close(actual.GetX(), 2.) && close(actual.GetY(), 2.936) && close(actual.GetHeading(), yaw+.2), "sensor offset/yaw applied incorrectly");
    if (valid) {
      const auto &points = scan.GetPointReadings(false);
      check(points.size() == 3, "localized scan point count differs from configured sensor");
      if (points.size() == 3) check(close(points[1].GetX(), 2.+.5*std::cos(yaw+.2)) &&
        close(points[1].GetY(), 2.936+.5*std::sin(yaw+.2)), "center beam offset applied more than once");
    }
    FixedGrid grid(16,16,.5); if (valid) grid.AddScan(&scan); grid.Update();
    check(grid.pass(4,7) == 6 && grid.hit(4,7) == 3 && grid.state(4,7) == 100,
          "three configured beams must contribute actual endpoint counters");
    std::ostringstream out; out << std::setprecision(17) << "{\"validated\":" << (valid ? "true" : "false")
      << ",\"expected_beams\":" << sensor.laser->GetNumberOfRangeReadings() << ",\"actual_beams\":" << scan.GetNumberOfRangeReadings()
      << ",\"sensor_pose\":[" << actual.GetX() << ',' << actual.GetY() << ',' << actual.GetHeading()
      << "],\"three_beam_endpoint\":" << grid.cell(4,7) << '}';
    return out.str();
  });
  run_case("wrong_beam_count_rejected_before_addscan", [] {
    Sensor sensor("cpu_wrong_count", 3); FixedGrid grid;
    karto::LocalizedRangeScan scan(karto::Name(sensor.name), karto::RangeReadingsVector{.5,.5});
    pose(scan, karto::Pose2(.1,.1,0.)); const bool valid = sensor.laser->Validate(&scan);
    check(!valid, "wrong beam count must be rejected by native Validate");
    if (valid) errors.push_back("unsafe AddScan intentionally not called even if validation unexpectedly accepted");
    check(grid.pass(0,0) == 0 && grid.hit(0,0) == 0, "rejected scan changed grid counters");
    return "{\"expected_beams\":3,\"actual_beams\":2,\"validated\":" + std::string(valid ? "true" : "false") +
      ",\"add_scan_called\":false,\"unchanged_cell\":" + grid.cell(0,0) + '}';
  });
  std::set<std::string> libraries; std::ifstream maps("/proc/self/maps"); std::string line;
  while (std::getline(maps, line)) if (line.find("/libkartoSlamToolbox.so") != std::string::npos) {
    auto start = line.find('/'); if (start != std::string::npos) libraries.insert(line.substr(start));
  }
  check(libraries.size() == 1, "expected exactly one actual loaded Karto SDK path");
  std::ifstream stat("/proc/self/stat"); std::string raw; std::getline(stat, raw); std::string start_ticks;
  const auto tail = raw.rfind(')');
  if (tail != std::string::npos) { std::istringstream fields(raw.substr(tail+2)); for (int i=0; i<=19; ++i) fields >> start_ticks; }
  const bool valid_start = !start_ticks.empty() && start_ticks.find_first_not_of("0123456789") == std::string::npos;
  check(valid_start, "could not read own start_ticks");
  std::cout.rdbuf(stdout_buffer);
  std::cout << "{\"schema\":\"mr3-karto-kernel-probe-v1\",\"scope\":\"fixed artificial SDK calls; native AddScan and explicit RayTrace ingress differ\","
    << "\"identity\":{\"pid\":" << getpid() << ",\"parent\":" << getppid() << ",\"group\":" << getpgrp()
    << ",\"session\":" << getsid(0) << ",\"start_ticks\":" << (valid_start ? start_ticks : "null")
    << "},\"loaded_karto_paths\":[";
  bool comma=false; for (const auto &path : libraries) { if (comma) std::cout << ','; std::cout << quote(path); comma=true; }
  std::cout << "],\"sdk_log\":" << quote(sdk_log.str()) << ",\"cases\":[";
  for (std::size_t i=0; i<results.size(); ++i) { if (i) std::cout << ','; std::cout << results[i]; }
  std::cout << "],\"errors\":[";
  for (std::size_t i=0; i<errors.size(); ++i) { if (i) std::cout << ','; std::cout << quote(errors[i]); }
  std::cout << "],\"passed\":" << (errors.empty() ? "true" : "false")
    << ",\"worlds_created\":0,\"nodes_created\":0,\"mapper_instances\":0,\"episodes\":0,\"policy_calls\":0,\"optimizer_steps\":0,"
    << "\"qualification\":false,\"training_eligible\":false,\"native_credit\":false}\n";
  return errors.empty() ? 0 : 1;
}
