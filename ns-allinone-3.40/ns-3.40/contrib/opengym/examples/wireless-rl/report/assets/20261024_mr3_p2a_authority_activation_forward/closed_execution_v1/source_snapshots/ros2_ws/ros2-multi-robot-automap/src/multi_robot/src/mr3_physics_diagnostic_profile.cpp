// Opt-in, diagnostic-only Gazebo Classic physics profile. Not a control node.
// Baseline reads only. Contrast sets exactly ODE quick-step iters once before
// the first physics update. This source must not be labeled a passive observer.
#include <gazebo/common/Events.hh>
#include <gazebo/common/Plugin.hh>
#include <gazebo/physics/PhysicsIface.hh>
#include <gazebo/physics/World.hh>
#include <gazebo/physics/ode/ODEPhysics.hh>
#include <gazebo/ode/ode.h>
#include <nlohmann/json.hpp>
#include <boost/any.hpp>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <dlfcn.h>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <memory>
#include <stdexcept>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

#ifndef MR3_PHYSICS_DIAGNOSTIC_SOURCE_SHA256
#define MR3_PHYSICS_DIAGNOSTIC_SOURCE_SHA256 "unconfigured_candidate_no_native_admission"
#endif

namespace mr3_diagnostics
{
namespace
{
using Json = nlohmann::json;
constexpr const char * kConfigEnv = "MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE";
void ProfileLibraryAnchor() {}

int64_t Ns(const gazebo::common::Time & value)
{
  return static_cast<int64_t>(value.sec) * 1000000000LL + value.nsec;
}

bool SameStat(const struct stat & a, const struct stat & b)
{
  return a.st_dev == b.st_dev && a.st_ino == b.st_ino && a.st_size == b.st_size &&
    a.st_mtim.tv_sec == b.st_mtim.tv_sec && a.st_mtim.tv_nsec == b.st_mtim.tv_nsec;
}

std::string ReadBinding(const std::string & path)
{
  struct stat before{}, after{};
  std::unique_ptr<std::FILE, decltype(&std::fclose)> input(std::fopen(path.c_str(), "rb"), &std::fclose);
  if (!input || ::fstat(::fileno(input.get()), &before) != 0) {
    throw std::runtime_error("diagnostic binding open/stat failed");
  }
  std::string raw;
  char block[4096];
  size_t count;
  while ((count = std::fread(block, 1, sizeof(block), input.get())) != 0) {
    raw.append(block, count);
  }
  struct stat linked{};
  if (std::ferror(input.get()) || ::fstat(::fileno(input.get()), &after) != 0 ||
    ::stat(path.c_str(), &linked) != 0 || !SameStat(before, after) || !SameStat(after, linked) ||
    raw.size() != static_cast<size_t>(after.st_size))
  {throw std::runtime_error("diagnostic binding changed while read");}
  return raw;
}

void RequireFinite(const Json & value)
{
  if (value.is_number_float() && !std::isfinite(value.get<double>())) {
    throw std::runtime_error("nonfinite diagnostic physics readback");
  }
  if (value.is_structured()) {
    for (const auto & item : value) {RequireFinite(item);}
  }
}

Json CachedParameter(const gazebo::physics::PhysicsEnginePtr & engine, const std::string & key)
{
  boost::any value;
  if (!engine->GetParam(key, value)) {
    throw std::runtime_error("required diagnostic parameter unavailable: " + key);
  }
  Json out{{"cpp_type", value.type().name()}};
  if (const auto p = boost::any_cast<double>(&value)) {out["value"] = *p;}
  else if (const auto p = boost::any_cast<int>(&value)) {out["value"] = *p;}
  else if (const auto p = boost::any_cast<unsigned int>(&value)) {out["value"] = *p;}
  else if (const auto p = boost::any_cast<bool>(&value)) {out["value"] = *p;}
  else if (const auto p = boost::any_cast<std::string>(&value)) {out["value"] = *p;}
  else {throw std::runtime_error("required diagnostic parameter unsupported type: " + key);}
  return out;
}

Json Snapshot(const gazebo::physics::WorldPtr & world)
{
  const auto engine = world->Physics();
  const auto ode = boost::dynamic_pointer_cast<gazebo::physics::ODEPhysics>(engine);
  if (!ode || !ode->GetWorldId()) {throw std::runtime_error("diagnostic requires actual ODE engine");}
  const auto id = ode->GetWorldId();
  Json cached;
  for (const auto & key : {"solver_type", "iters", "precon_iters", "sor", "cfm", "erp",
    "contact_max_correcting_vel", "contact_surface_layer", "max_contacts", "min_step_size",
    "sor_lcp_tolerance", "use_dynamic_moi_rescaling", "friction_model", "world_step_solver"})
  {cached[key] = CachedParameter(engine, key);}
  dVector3 gravity;
  dWorldGetGravity(id, gravity);
  Json native{{"iters", dWorldGetQuickStepNumIterations(id)},
    {"precon_iters", dWorldGetQuickStepPreconIterations(id)},
    {"sor", dWorldGetQuickStepW(id)}, {"cfm", dWorldGetCFM(id)}, {"erp", dWorldGetERP(id)},
    {"contact_max_correcting_vel", dWorldGetContactMaxCorrectingVel(id)},
    {"contact_surface_layer", dWorldGetContactSurfaceLayer(id)},
    {"sor_lcp_tolerance", dWorldGetQuickStepTolerance(id)},
    {"use_dynamic_moi_rescaling", dWorldGetQuickStepInertiaRatioReduction(id)},
    {"friction_model_enum", static_cast<int>(dWorldGetQuickStepFrictionModel(id))},
    {"gravity_xyz", {gravity[0], gravity[1], gravity[2]}}};
  const auto g = world->Gravity();
  return {{"engine_type", engine->GetType()}, {"cached", cached}, {"native_ode", native},
    {"max_step_size_sec", engine->GetMaxStepSize()},
    {"real_time_update_rate", engine->GetRealTimeUpdateRate()},
    {"target_real_time_factor", engine->GetTargetRealTimeFactor()},
    {"world_gravity_xyz", {g.X(), g.Y(), g.Z()}},
    {"engine_sdf", engine->GetSDF()->ToString("")}};
}

Json Invariants(Json value)
{
  value["cached"].erase("iters");
  value["native_ode"].erase("iters");
  // Exact original and new full engine SDF are both retained in the ledger.
  // Structured readbacks above, not SDF whitespace, define unchanged fields.
  value.erase("engine_sdf");
  return value;
}
}  // namespace

class ProfileState
{
public:
  Json binding;
  std::string binding_raw;
  std::string binding_path;
  std::string loaded_library;
  gazebo::physics::WorldPtr world;
  gazebo::event::ConnectionPtr created;
  gazebo::event::ConnectionPtr update;
  std::unique_ptr<std::FILE, decltype(&std::fclose)> output{nullptr, &std::fclose};
  bool applied{false};

  void FirstUpdate(const gazebo::common::UpdateInfo & info)
  {
    // Keep an empty, constant-time callback after success rather than disconnect
    // a Connection from inside its own dispatch. No further getters, writes or
    // setters are called once applied is true; only one setter is possible.
    if (applied) {return;}
    // A late profile is a failure, not permission to alter a running task.
    if (info.worldName != binding.at("world_name").get<std::string>() ||
      world->Iterations() != 1 || Ns(info.simTime) != 1000000LL ||
      world->Physics()->GetMaxStepSize() != 0.001)
    {throw std::runtime_error("physics diagnostic missed exact first1ms update boundary");}
    const Json before = Snapshot(world);
    RequireFinite(before);
    if (before.at("engine_type") != "ode" ||
      before.at("cached").at("solver_type").at("value") != "quick" ||
      before.at("cached").at("iters").at("value") != 50 ||
      before.at("native_ode").at("iters") != 50 ||
      before.at("cached").at("sor").at("value") != 1.3 ||
      before.at("native_ode").at("sor") != 1.3)
    {throw std::runtime_error("physics diagnostic baseline profile differs from declaration");}
    const bool contrast = binding.at("mode") == "iters150";
    if (contrast && !world->Physics()->SetParam("iters", boost::any(int(150)))) {
      throw std::runtime_error("diagnostic ODE iteration setter failed");
    }
    const Json after = Snapshot(world);
    RequireFinite(after);
    const int expected = contrast ? 150 : 50;
    if (after.at("cached").at("iters").at("value") != expected ||
      after.at("native_ode").at("iters") != expected ||
      Invariants(before).dump() != Invariants(after).dump())
    {throw std::runtime_error("physics diagnostic actual readback/invariants mismatch");}
    const Json row{{"schema", "mr3-physics-diagnostic-profile-v1"},
      {"kind", "first_boundary_profile"}, {"epoch", binding.at("epoch")},
      {"record_sequence", 1}, {"world_name", info.worldName},
      {"process_id", ::getpid()},
      {"sim_time_ns", Ns(info.simTime)}, {"world_iterations", world->Iterations()},
      {"wall_monotonic_ns", std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now().time_since_epoch()).count()},
      {"binding_path", binding_path}, {"binding_json", binding_raw},
      {"compiled_source_sha256", MR3_PHYSICS_DIAGNOSTIC_SOURCE_SHA256},
      {"loaded_library_path", loaded_library}, {"before", before}, {"after", after},
      {"mode", binding.at("mode")}, {"setter_call_count", contrast ? 1 : 0},
      {"scope", "diagnostic_first_boundary_configuration; not_control_or_continuous_physics_credit"}};
    const auto raw = row.dump() + "\n";
    if (std::fwrite(raw.data(), 1, raw.size(), output.get()) != raw.size() ||
      std::fflush(output.get()) != 0)
    {throw std::runtime_error("diagnostic profile ledger write failed");}
    applied = true;
  }
};

class PhysicsDiagnosticProfile : public gazebo::SystemPlugin
{
public:
  ~PhysicsDiagnosticProfile() override
  {
    auto state = std::move(state_);
    if (state) {state->created.reset(); state->update.reset();}
  }

  void Load(int, char **) override
  {
    const char * selected = std::getenv(kConfigEnv);
    if (!selected || !*selected) {
      throw std::invalid_argument("diagnostic profile loaded without explicit launch binding");
    }
    auto state = std::make_shared<ProfileState>();
    state->binding_path = std::filesystem::canonical(selected).string();
    state->binding_raw = ReadBinding(state->binding_path);
    // Trust boundary: this is the launch-generated exclusive binding, not the
    // user template. Launch strictly rejects duplicate/nonfinite template JSON.
    // The exact raw binding consumed here is retained for independent byte/SHA
    // comparison against the launch selection marker and archived binding.
    state->binding = Json::parse(state->binding_raw);
    const auto & binding = state->binding;
    if (binding.at("schema") != "mr3-physics-diagnostic-binding-v1" ||
      !binding.at("epoch").is_string() || binding.at("epoch").get<std::string>().empty() ||
      (binding.at("mode") != "baseline" && binding.at("mode") != "iters150") ||
      binding.at("profile_library").at("source_sha256") != MR3_PHYSICS_DIAGNOSTIC_SOURCE_SHA256)
    {throw std::invalid_argument("diagnostic binding/source/mode mismatch");}
    const std::filesystem::path directory = binding.at("episode_directory").get<std::string>();
    const std::filesystem::path output = binding.at("profile_output_path").get<std::string>();
    if (!directory.is_absolute() || output != directory / "physics_profile.jsonl" ||
      state->binding_path != (directory / "physics_diagnostic_binding.json").string())
    {throw std::invalid_argument("diagnostic profile output/binding episode mismatch");}
    Dl_info loaded{};
    if (!dladdr(reinterpret_cast<void *>(&ProfileLibraryAnchor), &loaded) || !loaded.dli_fname) {
      throw std::runtime_error("diagnostic actual library path unavailable");
    }
    state->loaded_library = std::filesystem::canonical(loaded.dli_fname).string();
    if (state->loaded_library != binding.at("profile_library").at("resolved_path")) {
      throw std::runtime_error("diagnostic loaded library path mismatch");
    }
    state->output.reset(std::fopen(output.c_str(), "wx"));
    if (!state->output) {throw std::runtime_error("diagnostic profile output already exists or cannot open");}
    state->created = gazebo::event::Events::ConnectWorldCreated(
      [weak = std::weak_ptr<ProfileState>(state)](const std::string & name) {
        if (auto current = weak.lock()) {
          if (current->world || name != current->binding.at("world_name")) {
            throw std::runtime_error("diagnostic received unexpected/duplicate world");
          }
          current->world = gazebo::physics::get_world(name);
          // WorldCreated precedes World::Init/PresetManager. Defer the one
          // allowed setter until the first update after initialization.
          current->update = gazebo::event::Events::ConnectWorldUpdateBegin(
            [weak](const gazebo::common::UpdateInfo & info) {
              if (auto active = weak.lock()) {active->FirstUpdate(info);}
            });
        }
      });
    state_ = std::move(state);
  }

private:
  std::shared_ptr<ProfileState> state_;
};
GZ_REGISTER_SYSTEM_PLUGIN(PhysicsDiagnosticProfile)
}  // namespace mr3_diagnostics
