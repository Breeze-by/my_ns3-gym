// Passive, opt-in diagnostic SensorPlugin. No ray recast or physical setters.
#include <gazebo/physics/PhysicsIface.hh>
#include <gazebo/common/Plugin.hh>
#include <gazebo/physics/Collision.hh>
#include <gazebo/physics/Link.hh>
#include <gazebo/physics/Model.hh>
#include <gazebo/physics/MultiRayShape.hh>
#include <gazebo/physics/RayShape.hh>
#include <gazebo/physics/Shape.hh>
#include <gazebo/physics/World.hh>
#include <gazebo/sensors/RaySensor.hh>
#include <nlohmann/json.hpp>

#include <atomic>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <dlfcn.h>
#include <fcntl.h>
#include <filesystem>
#include <iomanip>
#include <limits>
#include <memory>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unistd.h>

#ifndef MR3_RAY_PROVENANCE_SOURCE_SHA256
#error "Exact source SHA must be supplied by the build"
#endif

namespace multi_robot {
namespace ray_provenance {
using Json = nlohmann::json;

static void LibraryAnchor() {}

static std::int64_t Ns(const gazebo::common::Time &time) {
  return static_cast<std::int64_t>(time.sec) * 1000000000LL + time.nsec;
}

static std::int64_t WindowNs(const std::string &text) {
  if (text.empty() || text.find_first_not_of("0123456789") != std::string::npos)
    throw std::runtime_error("invalid_integer_nanosecond_window");
  return std::stoll(text);
}

static Json Floating(double value) {
  std::uint64_t bits;
  static_assert(sizeof(bits) == sizeof(value), "binary64 representation");
  std::memcpy(&bits, &value, sizeof(value));
  std::ostringstream text;
  text << std::hex << std::setfill('0') << std::setw(16) << bits;
  const char *kind = std::isnan(value) ? "nan" :
      (std::isinf(value) ? (std::signbit(value) ? "negative_infinity" : "positive_infinity") : "finite");
  return {{"value", std::isfinite(value) ? Json(value) : Json(nullptr)},
          {"fpclass", kind}, {"binary64_hex", text.str()}};
}

static Json Vector(const ignition::math::Vector3d &value) {
  if (!std::isfinite(value.X()) || !std::isfinite(value.Y()) || !std::isfinite(value.Z()))
    return {{"available", false}, {"reason", "nonfinite_vector"},
            {"components", {Floating(value.X()), Floating(value.Y()), Floating(value.Z())}}};
  return Json::array({value.X(), value.Y(), value.Z()});
}

static Json Pose(const ignition::math::Pose3d &value) {
  const auto &q = value.Rot();
  Json rotation;
  if (std::isfinite(q.W()) && std::isfinite(q.X()) && std::isfinite(q.Y()) && std::isfinite(q.Z()))
    rotation = Json::array({q.W(), q.X(), q.Y(), q.Z()});
  else
    rotation = {{"available", false}, {"reason", "nonfinite_quaternion"},
                {"components_wxyz", {Floating(q.W()), Floating(q.X()), Floating(q.Y()), Floating(q.Z())}}};
  return {{"position_xyz", Vector(value.Pos())}, {"quaternion_wxyz", rotation}};
}

static bool CurrentShortenedRay(double length, double fullRange) {
  return std::isfinite(length) && std::isfinite(fullRange) &&
      fullRange > 0.0 && length >= 0.0 && length < fullRange;
}

static std::string LoadedLibrary() {
  Dl_info info{};
  if (!dladdr(reinterpret_cast<void *>(&LibraryAnchor), &info) || !info.dli_fname)
    throw std::runtime_error("dladdr_library_unavailable");
  return std::filesystem::canonical(info.dli_fname).string();
}

struct State : std::enable_shared_from_this<State> {
  boost::weak_ptr<gazebo::physics::Model> model;
  boost::weak_ptr<gazebo::physics::World> world;
  std::weak_ptr<gazebo::sensors::RaySensor> sensor;
  gazebo::event::ConnectionPtr scanConnection;
  std::string epoch, robot, sensorLink, sensorName, library;
  std::int64_t startNs = 0, endNs = 0;
  std::int64_t lastMeasurementNs = -1;
  std::uint64_t sequence = 0, scanSequence = 0;
  std::atomic<bool> failed{false};
  std::mutex outputMutex;
  int fd = -1;

  ~State() {
    scanConnection.reset();
    if (fd >= 0) ::close(fd);
  }

  void Emit(Json value) {
    std::lock_guard<std::mutex> lock(outputMutex);
    value["schema"] = "mr3-ray-provenance-audit-v1";
    value["record_sequence"] = ++sequence;
    value["epoch"] = epoch;
    value["robot"] = robot;
    value["process_id"] = ::getpid();
    std::string raw = value.dump() + "\n";
    std::size_t offset = 0;
    while (offset < raw.size()) {
      const auto count = ::write(fd, raw.data() + offset, raw.size() - offset);
      if (count < 0 && errno == EINTR) continue;
      if (count <= 0) throw std::runtime_error("ray_diagnostic_write_failed");
      offset += static_cast<std::size_t>(count);
    }
  }

  void Failure(const std::string &reason) noexcept {
    if (failed.exchange(true)) return;
    try { Emit({{"kind", "diagnostic_error"}, {"error", reason}}); }
    catch (...) {}
    gzerr << "MR3 passive ray diagnostic failed: " << reason << "\n";
  }

  Json Collision(const std::string &name, const gazebo::physics::WorldPtr &clock) {
    auto collision = boost::dynamic_pointer_cast<gazebo::physics::Collision>(clock->EntityByName(name));
    if (!collision) return {{"available", false}, {"reason", "scoped_collision_lookup_unavailable"}, {"name", name}};
    Json result = {{"available", true}, {"scoped_name", collision->GetScopedName()},
                   {"geometry_scope", "Collision SDF and current Gazebo getters; not native ODE geometry readback."},
                   {"world_pose_current", Pose(collision->WorldPose())},
                   {"relative_pose_current", Pose(collision->RelativePose())}};
    if (auto parent = collision->GetLink()) {
      result["parent_link"] = parent->GetScopedName();
      result["parent_link_world_pose_current"] = Pose(parent->WorldPose());
    }
    if (auto shape = collision->GetShape()) result["shape_scale_current"] = Vector(shape->Scale());
    auto sdf = collision->GetSDF();
    result["sdf_available"] = static_cast<bool>(sdf);
    if (sdf) result["collision_sdf"] = sdf->ToString("");
    return result;
  }

  void Capture() noexcept {
    if (failed.load()) return;
    try {
      auto current = sensor.lock();
      auto clock = world.lock();
      auto owner = model.lock();
      if (!current || !clock || !owner) throw std::runtime_error("capture_owner_expired");
      const auto measurement = Ns(current->LastMeasurementTime());
      if (measurement < startNs || measurement > endNs) return;
      if (measurement <= lastMeasurementNs) throw std::runtime_error("measurement_time_not_strictly_increasing");
      lastMeasurementNs = measurement;
      const auto beforeClock = Ns(clock->SimTime());
      const auto beforeIteration = clock->Iterations();
      auto parent = owner->GetLink(sensorLink);
      auto base = owner->GetLink("base_link");
      if (!parent || !base) throw std::runtime_error("capture_link_missing");
      auto shape = current->LaserShape();
      const double min = shape->GetMinRange(), max = shape->GetMaxRange(), full = max - min;
      Json row = {{"kind", "scan"}, {"scan_sequence", ++scanSequence},
                  {"measurement_time_ns", measurement}, {"world_clock_before_ns", beforeClock},
                  {"world_iteration_before", beforeIteration}, {"sensor_scoped_name", current->ScopedName()},
                  {"sensor_parent", current->ParentName()}, {"parent_world_pose_current", Pose(parent->WorldPose())},
                  {"base_link_world_pose_current", Pose(base->WorldPose())},
                  {"model_world_pose_current", Pose(owner->WorldPose())},
                  {"sensor_pose_relative_to_parent", Pose(current->Pose())},
                  {"sensor_world_pose_current", Pose(current->Pose() + parent->WorldPose())},
                  {"parent_relative_to_base_current", Pose(parent->WorldPose() - base->WorldPose())},
                  {"range_min", min}, {"range_max", max}, {"full_ray_length", full},
                  {"ray_count", shape->RayCount()}, {"range_count", current->RangeCount()},
                  {"rays", Json::array()}, {"hit_collisions", Json::object()}};
      const bool oneToOne = shape->RayCount() == static_cast<unsigned>(current->RangeCount()) &&
                            current->VerticalRayCount() == 1 && current->VerticalRangeCount() == 1;
      row["final_range_one_to_one"] = oneToOne;
      for (unsigned index = 0; index < shape->RayCount(); ++index) {
        auto ray = shape->Ray(index);
        if (!ray) throw std::runtime_error("cached_ray_pointer_missing");
        ignition::math::Vector3d relativeStart, relativeEnd, globalStart, globalEnd;
        ray->RelativePoints(relativeStart, relativeEnd);
        ray->GlobalPoints(globalStart, globalEnd);
        const double length = ray->GetLength();
        const bool hit = CurrentShortenedRay(length, full);
        const std::string name = ray->CollisionName();
        Json item = {{"index", index}, {"cached_length", Floating(length)},
                     {"geometry_range", Floating(shape->GetRange(index))},
                     {"current_shortened_ray", hit}, {"cached_collision_name", name},
                     {"collision_name_current_hit_valid", hit && !name.empty()},
                     {"relative_start", Vector(relativeStart)}, {"relative_end_after_collision", Vector(relativeEnd)},
                     {"global_cast_start", Vector(globalStart)}, {"global_cast_end_before_collision", Vector(globalEnd)}};
        if (oneToOne) item["final_sensor_range"] = Floating(current->Range(index));
        if (hit) {
          const auto direction = globalEnd - globalStart;
          const double norm = direction.Length();
          if (std::isfinite(norm) && norm > 0)
            item["hit_point_from_cached_cast"] = Vector(globalStart + direction * (length / norm));
          if (!name.empty() && !row["hit_collisions"].contains(name))
            row["hit_collisions"][name] = Collision(name, clock);
        }
        row["rays"].push_back(std::move(item));
      }
      row["world_clock_after_ns"] = Ns(clock->SimTime());
      row["world_iteration_after"] = clock->Iterations();
      row["measurement_time_after_ns"] = Ns(current->LastMeasurementTime());
      row["pose_scope"] = "Current getters during Sensor::ConnectUpdated; world may advance during reads. Cached ray endpoints belong to original cast; no cast/pose atomicity claim.";
      row["collision_name_scope"] = "Current only for finite 0<=cached_length<max-min and nonempty name; otherwise name may be stale.";
      Emit(std::move(row));
    } catch (const std::exception &error) { Failure(error.what()); }
    catch (...) { Failure("unknown_scan_capture_error"); }
  }
};
}  // namespace ray_provenance

class RayProvenanceObserver : public gazebo::SensorPlugin {
 public:
  ~RayProvenanceObserver() override {
    if (state_) {
      state_->scanConnection.reset();
      state_.reset();
    }
  }

  void Load(gazebo::sensors::SensorPtr sensor, sdf::ElementPtr sdf) override {
    auto state = std::make_shared<ray_provenance::State>();
    state_ = state;
    try {
      auto ray = std::dynamic_pointer_cast<gazebo::sensors::RaySensor>(sensor);
      if (!ray) throw std::runtime_error("sensor_plugin_requires_ray_sensor");
      auto world = gazebo::physics::get_world(ray->WorldName());
      if (!world) throw std::runtime_error("sensor_world_missing");
      auto parent = boost::dynamic_pointer_cast<gazebo::physics::Link>(world->EntityByName(ray->ParentName()));
      if (!parent) throw std::runtime_error("sensor_parent_link_missing");
      auto model = parent->GetModel();
      if (!model) throw std::runtime_error("sensor_parent_model_missing");
      state->model = model;
      state->world = world;
      state->sensor = ray;
      state->epoch = sdf->Get<std::string>("epoch");
      state->robot = sdf->Get<std::string>("robot");
      state->sensorLink = sdf->Get<std::string>("sensor_link");
      state->sensorName = sdf->Get<std::string>("sensor_name");
      state->startNs = ray_provenance::WindowNs(sdf->Get<std::string>("start_ns"));
      state->endNs = ray_provenance::WindowNs(sdf->Get<std::string>("end_ns"));
      if (state->epoch.empty() || state->robot != model->GetName() ||
          state->sensorLink != parent->GetName() || state->sensorName != ray->Name() ||
          state->startNs < 0 || state->endNs < state->startNs || state->endNs > 300000000000LL)
        throw std::runtime_error("invalid_ray_diagnostic_identity_or_window");
      auto shape = ray->LaserShape();
      if (!shape || shape->RayCount() == 0) throw std::runtime_error("ray_shape_not_initialized_before_plugin_load");
      const auto path = sdf->Get<std::string>("output_path");
      if (!std::filesystem::path(path).is_absolute()) throw std::runtime_error("output_path_not_absolute");
      state->fd = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0644);
      if (state->fd < 0) throw std::runtime_error("exclusive_output_open_failed");
      state->library = ray_provenance::LoadedLibrary();
      state->Emit({{"kind", "configuration"}, {"compiled_source_sha256", MR3_RAY_PROVENANCE_SOURCE_SHA256},
                   {"plugin_type", "SensorPlugin"}, {"loaded_library_path", state->library}, {"output_path", path},
                   {"model_name", model->GetName()}, {"model_scoped_name", model->GetScopedName()},
                   {"world_name", world->Name()}, {"sensor_link", state->sensorLink},
                   {"sensor_name", state->sensorName}, {"start_ns", state->startNs}, {"end_ns", state->endNs},
                   {"callback", "Sensor::ConnectUpdated registered during SensorPlugin::Load before first sensor update"},
                   {"physics_lock", "No additional physics lock; original ray cache and current pose getter times distinguished."},
                   {"scope", "Passive diagnostic only; no publish, physics/sensor setter, ray update/recast, actor input or task credit."}});
      state->Emit({{"kind", "sensor_connected"}, {"world_clock_ns", ray_provenance::Ns(world->SimTime())},
                   {"sensor_scoped_name", ray->ScopedName()}, {"sensor_parent", ray->ParentName()},
                   {"sensor_pose_relative_to_parent", ray_provenance::Pose(ray->Pose())},
                   {"parent_world_pose_current", ray_provenance::Pose(parent->WorldPose())},
                   {"ray_count", shape->RayCount()}, {"horizontal_ray_count", ray->RayCount()},
                   {"range_count", ray->RangeCount()}, {"vertical_ray_count", ray->VerticalRayCount()},
                   {"range_min", ray->RangeMin()}, {"range_max", ray->RangeMax()},
                   {"range_resolution", ray->RangeResolution()}, {"sensor_update_rate", ray->UpdateRate()},
                   {"scope", "Existing initialized sensor; registration before sensor-container updates. No activation/rate changes."}});
      std::weak_ptr<ray_provenance::State> weak = state;
      state->scanConnection = ray->ConnectUpdated([weak]() {
        if (auto current = weak.lock()) current->Capture();
      });
    } catch (const std::exception &error) { state->Failure(error.what()); }
    catch (...) { state->Failure("unknown_sensor_plugin_load_error"); }
  }

 private:
  std::shared_ptr<ray_provenance::State> state_;
};

GZ_REGISTER_SENSOR_PLUGIN(RayProvenanceObserver)
}  // namespace multi_robot

#ifdef MR3_RAY_PROVENANCE_CPU_TEST
#include <cassert>
#include <iostream>
int main() {
  using namespace multi_robot::ray_provenance;
  assert(CurrentShortenedRay(.01, 9.88));
  assert(CurrentShortenedRay(0, 9.88));
  assert(!CurrentShortenedRay(9.88, 9.88));
  assert(!CurrentShortenedRay(std::nextafter(9.88, std::numeric_limits<double>::infinity()), 9.88));
  assert(!CurrentShortenedRay(-.01, 9.88));
  assert(!CurrentShortenedRay(std::numeric_limits<double>::quiet_NaN(), 9.88));
  assert(Floating(std::numeric_limits<double>::infinity())["fpclass"] == "positive_infinity");
  assert(Floating(-std::numeric_limits<double>::infinity())["value"].is_null());
  assert(Floating(-0.0)["binary64_hex"] == "8000000000000000");
  assert(WindowNs("0") == 0 && WindowNs("300000000000") == 300000000000LL);
  bool rejected = false;
  try { WindowNs("-1"); } catch (const std::runtime_error &) { rejected = true; }
  assert(rejected);
  auto nonfinite = Vector({std::numeric_limits<double>::quiet_NaN(), 0, 1});
  assert(nonfinite["available"] == false && !nonfinite.dump().empty());
  ignition::math::Pose3d parent(1, 2, 3, 0, 0, .3), relative(-.064, 0, .121, 0, 0, 0);
  const auto expected = parent.CoordPositionAdd(relative.Pos());
  assert(((relative + parent).Pos() - expected).Length() < 1e-14);
  std::cout << "PASS 13 pure assertion groups; no Gazebo/ROS initialization or native run\n";
}
#endif
