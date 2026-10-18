// Gazebo Classic SystemPlugin: install the independently testable ray/box
// narrowphase correction once, before any sensor in the MR3 world can scan.
// No range filtering, sensor setters, recasting or non-ray-box collider changes.
#include "multi_robot/mr3_ray_box_collision.hpp"

#include <gazebo/common/Events.hh>
#include <gazebo/common/Plugin.hh>
#include <gazebo/physics/physics.hh>
#include <gazebo/physics/ode/ODEPhysics.hh>
#include <nlohmann/json.hpp>
#include <dlfcn.h>
#include <fcntl.h>
#include <unistd.h>
#include <atomic>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>

#ifndef MR3_RAY_BOX_CORRECTOR_SOURCE_SHA256
#define MR3_RAY_BOX_CORRECTOR_SOURCE_SHA256 "unconfigured"
#endif
#ifndef MR3_RAY_BOX_COLLISION_SOURCE_SHA256
#define MR3_RAY_BOX_COLLISION_SOURCE_SHA256 "unconfigured"
#endif
#ifndef MR3_RAY_BOX_COLLISION_HEADER_SHA256
#define MR3_RAY_BOX_COLLISION_HEADER_SHA256 "unconfigured"
#endif

namespace multi_robot
{
namespace
{
using Json = nlohmann::json;

std::int64_t TimeNs(const gazebo::common::Time &value)
{
  return static_cast<std::int64_t>(value.sec) * 1000000000LL + value.nsec;
}

struct Packet
{
  ray_box::Input input{};
  ray_box::Result result{};
  bool ray_body_is_null = false;
};

// One immutable primitive snapshot. A single winning writer owns state 1;
// release/acquire publishes the completed fixed-size packet. It is never reset,
// so the physics thread's one read cannot race a later overwrite.
struct OneShot
{
  std::atomic<unsigned int> state{0};
  Packet packet{};
  void Offer(const Packet &value) noexcept
  {
    unsigned int expected = 0;
    if (state.compare_exchange_strong(expected, 1, std::memory_order_acq_rel))
    {
      packet = value;
      state.store(2, std::memory_order_release);
    }
  }
};

struct Runtime
{
  int fd = -1;
  std::string epoch;
  std::string output;
  std::string world;
  std::string library;
  std::string odeLibrary;
  std::mutex outputMutex;
  std::atomic<std::uint64_t> calls{0}, hits{0}, misses{0}, nearParallel{0};
  std::atomic<std::uint64_t> errors{0};
  OneShot first, firstOutsideNearParallel;

  void Emit(const std::string &kind, Json fields)
  {
    fields["schema"] = "mr3-ray-box-corrector-audit-v1";
    fields["kind"] = kind;
    fields["epoch"] = epoch;
    fields["process_id"] = ::getpid();
    const std::string bytes = fields.dump() + "\n";
    std::lock_guard<std::mutex> lock(outputMutex);
    std::size_t written = 0;
    while (written < bytes.size())
    {
      const auto n = ::write(fd, bytes.data() + written, bytes.size() - written);
      if (n < 0 && errno == EINTR) continue;
      if (n <= 0) throw std::runtime_error("ray-box audit write failed");
      written += static_cast<std::size_t>(n);
    }
  }

  Json Counts() const
  {
    return {{"callback_calls", calls.load()}, {"hits", hits.load()},
      {"misses", misses.load()}, {"nonzero_nearparallel_calls", nearParallel.load()},
      {"callback_errors", errors.load()}};
  }

  ~Runtime()
  {
    if (fd >= 0)
    {
      // No registration reversal occurs: this module stays resident with
      // Gazebo's PluginT (dlclose disabled). Normal server shutdown stops all
      // calling threads before process-global destruction.
      try { Emit("process_lifetime_summary", Counts()); } catch (...) {}
      ::fsync(fd);
      ::close(fd);
    }
  }
};

// The global owner outlives the SystemPlugin object; registered callback and
// primitive buffers remain valid until process teardown. No callback captures
// a World or plugin strong pointer.
std::shared_ptr<Runtime> processRuntime;
std::atomic<Runtime *> installedRuntime{nullptr};

int InstalledCollider(dGeomID ray, dGeomID box, int flags,
  dContactGeom *contact, int skip) noexcept
{
  Runtime *runtime = installedRuntime.load(std::memory_order_acquire);
  if (!runtime) return 0;  // Not reachable after successful installation.
  runtime->calls.fetch_add(1, std::memory_order_relaxed);
  try
  {
    if (!contact || skip < static_cast<int>(sizeof(dContactGeom)) ||
        (flags & 0xffff) == 0)
      throw std::runtime_error("invalid ray-box callback contact buffer");
    const auto input = ray_box::ReadInput(ray, box);
    const auto result = ray_box::Solve(input);
    const Packet packet{input, result, dGeomGetBody(ray) == nullptr};
    runtime->first.Offer(packet);
    bool near = false;
    bool outsideToward = false;
    for (int axis = 0; axis < 3; ++axis)
    {
      const auto value = input.direction[axis];
      const bool smallNonzero = value != 0 && std::abs(value) <= 1e-6;
      near = near || smallNonzero;
      const auto start = input.start[axis];
      const bool toward = (start > 0 && value < 0) || (start < 0 && value > 0);
      outsideToward = outsideToward || (smallNonzero && toward &&
        std::abs(start) > input.lengths[axis] / 2);
    }
    if (near)
    {
      runtime->nearParallel.fetch_add(1, std::memory_order_relaxed);
    }
    if (outsideToward) runtime->firstOutsideNearParallel.Offer(packet);
    if (result.hit) runtime->hits.fetch_add(1, std::memory_order_relaxed);
    else runtime->misses.fetch_add(1, std::memory_order_relaxed);
    return ray_box::WriteContact(ray, box, input, result, contact);
  }
  catch (...)
  {
    // The normal path has no JSON, heap allocation or I/O. Invalid-input
    // exceptions are contained here (constructing them may allocate). The next
    // world boundary records the invalid attempt and aborts world execution;
    // no invalid geometry is granted successful capture/task credit.
    runtime->errors.fetch_add(1, std::memory_order_relaxed);
    return 0;
  }
}

Json Primitive(const Packet &packet)
{
  const auto &in = packet.input;
  return {{"start_box_local", in.start}, {"direction_box_local", in.direction},
    {"box_lengths", in.lengths}, {"ray_start_world", in.world_start},
    {"ray_direction_world", in.world_direction}, {"box_rotation", in.box_rotation},
    {"finite_ray_length", in.max_length}, {"ray_body_is_null", packet.ray_body_is_null},
    {"corrected_hit", packet.result.hit},
    {"corrected_depth", packet.result.hit ? Json(static_cast<double>(packet.result.depth)) : Json(nullptr)},
    {"corrected_axis", packet.result.hit ? Json(packet.result.axis) : Json(nullptr)},
    {"scope", "Primitive copied inside actual collider callback. Nearparallel is a branch condition, not proof of a legacy false hit. No old collider shadow runs."}};
}

void Drain(Runtime &runtime, std::int64_t publishedClock)
{
  const auto emit = [&runtime, publishedClock](OneShot &slot, const char *kind)
  {
    unsigned int expected = 2;
    if (slot.state.compare_exchange_strong(expected, 3, std::memory_order_acq_rel))
    {
      auto row = Primitive(slot.packet);
      row["published_world_clock_ns"] = publishedClock;
      runtime.Emit(kind, std::move(row));
    }
  };
  emit(runtime.first, "first_actual_callback");
  emit(runtime.firstOutsideNearParallel, "first_outside_nearparallel_toward_slab");
  if (runtime.errors.load(std::memory_order_relaxed) != 0)
  {
    runtime.Emit("fatal_callback_input_error", runtime.Counts());
    throw std::runtime_error("ray-box correction encountered invalid native primitives");
  }
}

std::string RequiredEnvironment(const char *name)
{
  const char *value = std::getenv(name);
  if (!value || !*value) throw std::runtime_error(std::string("missing ") + name);
  return value;
}

std::string LoadedPath(const void *symbol)
{
  Dl_info info{};
  if (!dladdr(symbol, &info) || !info.dli_fname)
    throw std::runtime_error("ray-box library provenance unavailable");
  return std::filesystem::canonical(info.dli_fname).string();
}
}  // namespace

class RayBoxCorrector : public gazebo::SystemPlugin
{
  public: void Load(int, char **) override
  {
    if (processRuntime) throw std::runtime_error("ray-box SystemPlugin loaded twice");
    const auto runtime = std::make_shared<Runtime>();
    runtime->output = RequiredEnvironment("MR3_RAY_BOX_CORRECTOR_AUDIT_PATH");
    runtime->epoch = RequiredEnvironment("MR3_RAY_BOX_CORRECTOR_EPOCH");
    if (!std::filesystem::path(runtime->output).is_absolute())
      throw std::runtime_error("ray-box audit path must be absolute");
    runtime->library = LoadedPath(reinterpret_cast<const void *>(&InstalledCollider));
    runtime->odeLibrary = LoadedPath(reinterpret_cast<const void *>(&dCollide));
    runtime->fd = ::open(runtime->output.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0644);
    if (runtime->fd < 0) throw std::runtime_error("cannot exclusively create ray-box audit");
    runtime->Emit("configuration", {{"plugin_type", "SystemPlugin"},
      {"compiled_source_sha256", MR3_RAY_BOX_CORRECTOR_SOURCE_SHA256},
      {"compiled_collision_source_sha256", MR3_RAY_BOX_COLLISION_SOURCE_SHA256},
      {"compiled_collision_header_sha256", MR3_RAY_BOX_COLLISION_HEADER_SHA256},
      {"loaded_library_path", runtime->library}, {"actual_ode_library_path", runtime->odeLibrary},
      {"scope", "Process-global dRayClass/dBoxClass finite-segment correction; all other collider pairs unchanged. No raw range filtering."}});
    processRuntime = runtime;
    const std::weak_ptr<Runtime> weak = runtime;
    created = gazebo::event::Events::ConnectWorldCreated([weak](const std::string &name)
    {
      const auto state = weak.lock();
      if (!state) return;
      Json observed{{"world", name},
        {"installation_phase", "world_created_during_load_before_world_init"},
        {"world_iterations", nullptr}, {"world_iterations_available", false},
        {"world_iterations_unavailable_reason", "counter_initialized_only_in_World_Init"}};
      gazebo::physics::WorldPtr world;
      try { world = gazebo::physics::get_world(name); }
      catch (const std::exception &error) { observed["world_lookup_error"] = error.what(); }
      catch (...) { observed["world_lookup_error"] = "non_std_world_lookup_exception"; }
      const auto physics = world ? world->Physics() : gazebo::physics::PhysicsEnginePtr();
      const auto ode = boost::dynamic_pointer_cast<gazebo::physics::ODEPhysics>(physics);
      observed["world_lookup_succeeded"] = bool(world);
      observed["physics_available"] = bool(physics);
      observed["physics_type"] = physics ? Json(physics->GetType()) : Json(nullptr);
      observed["native_ode_world_available"] = bool(ode && ode->GetWorldId());
      observed["world_clock_ns"] = world ? Json(TimeNs(world->SimTime())) : Json(nullptr);
      observed["world_load_completed"] = world ? Json(world->IsLoaded()) : Json(nullptr);
      observed["world_sensors_initialized"] = world ? Json(world->SensorsInitialized()) : Json(nullptr);
      // Running() returns !stop; the constructor sets stop=false before Run.
      // Preserve its actual value without mistaking it for a thread-start flag.
      observed["world_running_getter"] = world ? Json(world->Running()) : Json(nullptr);
      std::size_t sensorCount = 0;
      if (world)
        for (const auto &model : world->Models())
          for (const auto &link : model->GetLinks()) sensorCount += link->GetSensorCount();
      observed["model_sensor_count"] = world ? Json(sensorCount) : Json(nullptr);
      Json failures = Json::array();
      if (!world) failures.push_back("world_lookup_failed");
      if (!physics) failures.push_back("physics_unavailable");
      else if (physics->GetType() != "ode") failures.push_back("physics_type_not_ode");
      if (world && TimeNs(world->SimTime()) != 0) failures.push_back("world_clock_not_zero");
      if (world && world->IsLoaded()) failures.push_back("world_load_already_completed");
      if (world && world->SensorsInitialized()) failures.push_back("world_sensors_already_initialized");
      if (world && sensorCount != 0) failures.push_back("model_sensor_already_created");
      if (!ode || !ode->GetWorldId()) failures.push_back("native_ode_world_unavailable");
      if (!failures.empty())
      {
        observed["failed_preconditions"] = failures;
        state->Emit("fatal_installation_precondition", observed);
        throw std::runtime_error("ray-box installation precondition failed: " + failures.dump());
      }
      const int nativeIterations = dWorldGetQuickStepNumIterations(ode->GetWorldId());
      const double maxStepSize = physics->GetMaxStepSize();
      state->world = name;
      Runtime *expected = nullptr;
      if (!installedRuntime.compare_exchange_strong(expected, state.get(), std::memory_order_acq_rel))
      {
        observed["failed_preconditions"] = Json::array({"process_runtime_already_installed"});
        state->Emit("fatal_installation_precondition", observed);
        throw std::runtime_error("ray-box collider already installed / second world unsupported");
      }
      dSetColliderOverride(dRayClass, dBoxClass, &InstalledCollider);
      observed["registered_pair"] = {"dRayClass", "dBoxClass"};
      observed["native_ode_quickstep_iterations"] = nativeIterations;
      observed["physics_max_step_size_sec"] = maxStepSize;
      observed["failed_preconditions"] = failures;
      observed["scope"] = "WorldCreated during World::Load, after ODE construction and before Load completes/World::Init/Run/sensor creation. The iteration counter is not initialized at this phase and is not read.";
      state->Emit("installed", std::move(observed));
    });
    ended = gazebo::event::Events::ConnectWorldUpdateEnd([weak]()
    {
      const auto state = weak.lock();
      if (!state || installedRuntime.load(std::memory_order_acquire) != state.get()) return;
      const auto world = gazebo::physics::get_world(state->world);
      Drain(*state, world ? TimeNs(world->SimTime()) : -1);
    });
  }

  public: ~RayBoxCorrector() override
  {
    created.reset();
    ended.reset();
    if (processRuntime)
    {
      try
      {
        Drain(*processRuntime, -1);
        auto counts = processRuntime->Counts();
        counts["scope"] = "Snapshot at SystemPlugin destruction; process-global callback state/code remains alive until process teardown.";
        processRuntime->Emit("plugin_destructor_snapshot", std::move(counts));
      }
      catch (...) {}
    }
  }

  private: gazebo::event::ConnectionPtr created, ended;
};
GZ_REGISTER_SYSTEM_PLUGIN(RayBoxCorrector)
}  // namespace multi_robot
