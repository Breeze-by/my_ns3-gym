// Disabled CPU adapter, not a ROS node, full Mapper, or quality qualification.
// C ABI v1 (ctypes): create returns a nonzero uint64 handle, or 0 on error.
// create(width:int32,height:int32,res,boundary_x,boundary_y,beams:uint32,
//        angle_min,angle_step,range_min,range_max,threshold,offset_x,offset_y,
//        offset_yaw,max_scans:uint64), with all untyped scalar arguments double.
// add_scan(handle,ranges:double*,count:uint32,estimated_body_x,y,yaw) returns
// 0 complete, 1 consumed partial/out-of-map, -1 error. No source-ID gate lives
// here: the Python owner must deduplicate exact payloads before calling SDK.
// export(handle,pass:uint32*,hit:uint32*,map:int8*,cells:uint64) returns 0/-1;
// arrays are caller-owned row-major width*height, with no SDK padding.
// world_to_grid(handle,x,y,out_x:int32*,out_y:int32*) and destroy(handle)
// return 0/-1. error() is thread-local and valid until the next ABI operation.
// Valid pointers of the documented capacity/alignment are the caller's duty.
// SDK mutation followed by an exception poisons the handle: only destroy is
// then allowed. Native false/partial is NOT an exception and consumes one scan.
// SDK center offset = public boundary origin + res/2 is this adapter's declared
// phase convention, different from native toNavMap's direct offset publication.
// Native AddScan min/max skips, threshold tolerance, beam weights and defaults
// are unchanged. No RayTrace/no-hit substitute, scan matching or truth input.

#include <karto_sdk/Karto.h>
#include <unistd.h>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <exception>
#include <limits>
#include <iostream>
#include <map>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <utility>

namespace {
using Vec = karto::Vector2<kt_double>;
using Index = karto::Vector2<kt_int32s>;
static_assert(sizeof(kt_int32u) == sizeof(std::uint32_t), "SDK counter ABI");

// Explicit supported-input/resource limits, not changes to the sensor model.
constexpr std::uint64_t kMaxCells = 8000000;
constexpr std::uint64_t kMaxRayVisits = 8000000;
constexpr std::uint32_t kMaxBeams = 4096;
constexpr double kMaxGridCoordinate = 1000000.;
constexpr double kMaxAngle = 1000000.;
thread_local char last_error[512] = {};
std::mutex sdk_mutex;  // Serializes this adapter's SensorManager/SDK instances.
struct SdkConsole {
  std::streambuf *previous = std::cout.rdbuf(std::cerr.rdbuf());
  ~SdkConsole() { std::cout.rdbuf(previous); }
};  // Keep SDK registration logs off the worker's stdout IPC protocol.

void error(const char *message) noexcept {
  std::snprintf(last_error, sizeof(last_error), "%s", message);
}
void require(bool condition, const char *message) {
  if (!condition) throw std::invalid_argument(message);
}
bool is_finite(double value) { return std::isfinite(value); }
bool angle_ok(double value) { return is_finite(value) && std::abs(value) <= kMaxAngle; }

struct FixedGrid : karto::OccupancyGrid {
  FixedGrid(std::int32_t width, std::int32_t height, double resolution, const Vec &center)
  : karto::OccupancyGrid(width, height, center, resolution) {
    // The public constructor's counter grids are initially 0x0.
    karto::LocalizedRangeScanVector empty;
    karto::OccupancyGrid::CreateFromScans(empty);
  }
  using karto::OccupancyGrid::AddScan;
  using karto::OccupancyGrid::Update;
  using karto::OccupancyGrid::GetCellPassCounts;
  using karto::OccupancyGrid::GetCellHitsCounts;
};

struct Adapter {
  std::unique_ptr<FixedGrid> grid;
  std::unique_ptr<karto::LaserRangeFinder> laser;
  std::string name;
  std::uint32_t beams;
  std::uint64_t max_scans, consumed = 0;
  bool registered = false, poisoned = false;

  Adapter(std::uint64_t id, std::int32_t width, std::int32_t height, double resolution,
          double origin_x, double origin_y, std::uint32_t beam_count,
          double angle_min, double angle_step, double range_min, double range_max,
          double threshold, double offset_x, double offset_y, double offset_yaw,
          std::uint64_t scan_limit)
  : name("mr3_proxy2d_karto_v1_" + std::to_string(getpid()) + "_" + std::to_string(id)),
    beams(beam_count), max_scans(scan_limit) {
    require(width > 0 && height > 0 && width <= 32768 && height <= 32768,
            "unsupported grid dimensions");
    const auto padded_width = (std::uint64_t(width) + 7) & ~std::uint64_t(7);
    require(padded_width * std::uint64_t(height) <= kMaxCells, "grid cell limit exceeded");
    require(is_finite(resolution) && resolution > karto::KT_TOLERANCE && is_finite(1. / resolution),
            "unsupported resolution (must exceed SDK zero tolerance)");
    require(is_finite(origin_x) && is_finite(origin_y), "nonfinite boundary origin");
    const double center_x = origin_x + resolution / 2.;
    const double center_y = origin_y + resolution / 2.;
    require(is_finite(center_x) && is_finite(center_y) && center_x > origin_x && center_y > origin_y,
            "unrepresentable grid center phase");
    require(beams > 0 && beams <= kMaxBeams, "unsupported beam count");
    require(angle_ok(angle_min) && is_finite(angle_step) && angle_step > 0.,
            "invalid uniform angular configuration");
    const double angle_max = angle_min + double(beams - 1) * angle_step;
    require(angle_ok(angle_max), "unsupported maximum angle");
    // Every intermediate native setter calls Update() and casts its count.
    require(std::max(std::abs(angle_min), std::abs(angle_max)) / angle_step <
            double(std::numeric_limits<std::uint32_t>::max()) - 2.,
            "angular configuration exceeds native intermediate count");
    require(is_finite(range_min) && is_finite(range_max) && is_finite(threshold) &&
            range_min >= 0. && range_max > range_min &&
            threshold >= range_min && threshold <= range_max, "invalid range limits");
    require(is_finite(offset_x) && is_finite(offset_y) && angle_ok(offset_yaw), "invalid laser extrinsic");
    // Each beam can increment a cell once on TraceLine and once at its hit.
    require(max_scans > 0 && max_scans <=
            std::numeric_limits<std::uint32_t>::max() / (2ULL * beams),
            "scan budget could overflow native uint32 counters");
    grid = std::make_unique<FixedGrid>(width, height, resolution, Vec(center_x, center_y));
    laser.reset(karto::LaserRangeFinder::CreateLaserRangeFinder(
      karto::LaserRangeFinder_Custom, karto::Name(name)));
    require(bool(laser), "native sensor creation failed");
    laser->SetMinimumRange(range_min);
    laser->SetMaximumRange(range_max);
    laser->SetRangeThreshold(threshold);
    // Collapse to one beam before changing resolution; avoid invalid transient
    // counts even for a valid one-beam scan or a signed angular interval.
    laser->SetMinimumAngle(0.);
    laser->SetMaximumAngle(0.);
    laser->SetAngularResolution(angle_step);
    if (angle_min < 0.) {
      laser->SetMinimumAngle(angle_min);
      laser->SetMaximumAngle(angle_max);
    } else {
      laser->SetMaximumAngle(angle_max);
      laser->SetMinimumAngle(angle_min);
    }
    laser->SetIs360Laser(false);  // Caller count includes both configured ends.
    laser->SetOffsetPose(karto::Pose2(offset_x, offset_y, offset_yaw));
    require(laser->Validate() && laser->GetNumberOfRangeReadings() == beams,
            "native configured beam count does not match requested count");
    karto::SensorManager::GetInstance()->RegisterSensor(laser.get());
    registered = true;
  }

  void close() {
    if (registered) {
      karto::SensorManager::GetInstance()->UnregisterSensor(laser.get());
      registered = false;
    }
  }
  ~Adapter() noexcept {
    try { close(); }
    catch (...) {
      // Do not leave SensorManager with a dangling pointer on SDK cleanup error.
      // Normal destroy calls close explicitly and reports failure to the owner.
      laser.release();
    }
  }

  Index safe_index(double x, double y) const {
    require(is_finite(x) && is_finite(y), "nonfinite world coordinate");
    const auto *converter = grid->GetCoordinateConverter();
    const auto &center = converter->GetOffset();
    const double qx = (x - center.GetX()) * converter->GetScale();
    const double qy = (y - center.GetY()) * converter->GetScale();
    require(is_finite(qx) && is_finite(qy) && std::abs(qx) <= kMaxGridCoordinate &&
            std::abs(qy) <= kMaxGridCoordinate, "world coordinate exceeds safe native lattice");
    return grid->WorldToGrid(Vec(x, y));  // Native half-away-from-zero, no floor patch.
  }

  void preflight(karto::LocalizedRangeScan &scan) const {
    require(laser->Validate(&scan), "native scan Validate rejected input");
    const auto sensor = scan.GetSensorPose();  // Applies the body-to-laser offset once.
    require(angle_ok(sensor.GetHeading()), "unsupported computed sensor heading");
    const auto from = safe_index(sensor.GetX(), sensor.GetY());
    const auto &points = scan.GetPointReadings(false);
    require(points.size() == beams, "native point count mismatch");
    std::uint64_t visits = 0;
    for (std::uint32_t i = 0; i < beams; ++i) {
      const double range = scan.GetRangeReadings()[i];
      if (range <= laser->GetMinimumRange() || range >= laser->GetMaximumRange()) continue;
      auto point = points[i];
      if (range >= laser->GetRangeThreshold()) {
        const double ratio = laser->GetRangeThreshold() / range;
        point.SetX(sensor.GetX() + ratio * (point.GetX() - sensor.GetX()));
        point.SetY(sensor.GetY() + ratio * (point.GetY() - sensor.GetY()));
      }
      const auto to = safe_index(point.GetX(), point.GetY());
      // Includes out-of-map segments; SDK still walks their complete lattice.
      // Coordinate bound also protects signed subtraction and 2*error in TraceLine.
      visits += std::uint64_t(std::max(std::abs(to.GetX() - from.GetX()),
                                      std::abs(to.GetY() - from.GetY()))) + 1;
      require(visits <= kMaxRayVisits, "native ray-work limit exceeded");
    }
  }
};

std::map<std::uint64_t, std::unique_ptr<Adapter>> instances;
std::uint64_t next_handle = 1;  // Never reused, including failed create attempts.
Adapter &lookup(std::uint64_t handle, bool allow_poisoned = false) {
  const auto found = instances.find(handle);
  require(handle != 0 && found != instances.end(), "unknown or destroyed handle");
  require(allow_poisoned || !found->second->poisoned, "poisoned handle; destroy without retry");
  return *found->second;
}
std::int8_t map_value(kt_int8u state) {
  switch (state) {
    case karto::GridStates_Unknown: return -1;
    case karto::GridStates_Occupied: return 100;
    case karto::GridStates_Free: return 0;
    default: throw std::runtime_error("unexpected native grid state");
  }
}
}  // namespace

#define MR3_KARTO_CATCH(value) \
  catch (const karto::Exception &e) { error(e.GetErrorMessage().c_str()); return value; } \
  catch (const std::exception &e) { error(e.what()); return value; } \
  catch (...) { error("unknown native exception"); return value; }

extern "C" {
std::uint32_t mr3_karto_abi_version() noexcept { return 1; }
const char *mr3_karto_error() noexcept { return last_error; }

std::uint64_t mr3_karto_create(
    std::int32_t width, std::int32_t height, double resolution, double origin_x, double origin_y,
    std::uint32_t beams, double angle_min, double angle_step, double range_min, double range_max,
    double threshold, double offset_x, double offset_y, double offset_yaw,
    std::uint64_t max_scans) noexcept {
  error("");
  try {
    std::lock_guard<std::mutex> lock(sdk_mutex);
    SdkConsole console;
    require(next_handle < std::numeric_limits<std::uint64_t>::max(), "handle space exhausted");
    const auto handle = next_handle++;
    auto instance = std::make_unique<Adapter>(handle, width, height, resolution, origin_x, origin_y,
      beams, angle_min, angle_step, range_min, range_max, threshold, offset_x, offset_y, offset_yaw,
      max_scans);
    instances.emplace(handle, std::move(instance));
    return handle;
  } MR3_KARTO_CATCH(0)
}

std::int32_t mr3_karto_add_scan(std::uint64_t handle, const double *ranges, std::uint32_t count,
                               double body_x, double body_y, double body_yaw) noexcept {
  error("");
  try {
    std::lock_guard<std::mutex> lock(sdk_mutex);
    auto &instance = lookup(handle);
    require(ranges && count == instance.beams, "null ranges or wrong beam count");
    require(is_finite(body_x) && is_finite(body_y) && angle_ok(body_yaw), "invalid estimated body pose");
    require(instance.consumed < instance.max_scans, "scan budget exhausted");
    karto::RangeReadingsVector values;
    values.reserve(count);
    for (std::uint32_t i = 0; i < count; ++i) {
      require(is_finite(ranges[i]) && ranges[i] >= 0., "nonfinite or negative range");
      values.push_back(ranges[i]);
    }
    karto::LocalizedRangeScan scan(karto::Name(instance.name), values);
    const karto::Pose2 estimated(body_x, body_y, body_yaw);
    scan.SetOdometricPose(estimated);
    scan.SetCorrectedPose(estimated);  // Estimated input only; this does not estimate a pose.
    instance.preflight(scan);  // Validation/work bounds complete before any counter writes.
    ++instance.consumed;
    try {
      const bool complete = instance.grid->AddScan(&scan);
      instance.grid->Update();
      return complete ? 0 : 1;
    } catch (...) {
      instance.poisoned = true;
      throw;
    }
  } MR3_KARTO_CATCH(-1)
}

std::int32_t mr3_karto_export(std::uint64_t handle, std::uint32_t *passes, std::uint32_t *hits,
                             std::int8_t *states, std::uint64_t cells) noexcept {
  error("");
  try {
    std::lock_guard<std::mutex> lock(sdk_mutex);
    auto &instance = lookup(handle);
    auto &grid = *instance.grid;
    require(passes && hits && states && cells ==
      std::uint64_t(grid.GetWidth()) * std::uint64_t(grid.GetHeight()), "invalid export buffers/count");
    std::uint64_t output = 0;
    for (std::int32_t y = 0; y < grid.GetHeight(); ++y) {
      for (std::int32_t x = 0; x < grid.GetWidth(); ++x, ++output) {
        const Index index(x, y);
        passes[output] = grid.GetCellPassCounts()->GetValue(index);
        hits[output] = grid.GetCellHitsCounts()->GetValue(index);
        states[output] = map_value(grid.GetValue(index));
      }
    }
    return 0;
  } MR3_KARTO_CATCH(-1)
}

std::int32_t mr3_karto_world_to_grid(std::uint64_t handle, double x, double y,
                                    std::int32_t *out_x, std::int32_t *out_y) noexcept {
  error("");
  try {
    std::lock_guard<std::mutex> lock(sdk_mutex);
    auto &instance = lookup(handle);
    require(out_x && out_y, "null grid-index output");
    const auto index = instance.safe_index(x, y);
    *out_x = index.GetX();
    *out_y = index.GetY();
    return 0;
  } MR3_KARTO_CATCH(-1)
}

std::int32_t mr3_karto_destroy(std::uint64_t handle) noexcept {
  error("");
  try {
    std::lock_guard<std::mutex> lock(sdk_mutex);
    SdkConsole console;
    auto &instance = lookup(handle, true);
    instance.close();  // On cleanup error keep handle/sensor alive and report it.
    instances.erase(handle);
    return 0;
  } MR3_KARTO_CATCH(-1)
}
}  // extern "C"

#undef MR3_KARTO_CATCH
