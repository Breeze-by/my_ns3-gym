// Read-only, opt-in Gazebo Classic stop-response diagnostic observer.
#include <gazebo/common/Events.hh>
#include <gazebo/common/Plugin.hh>
#include <gazebo/physics/Joint.hh>
#include <gazebo/physics/Collision.hh>
#include <gazebo/physics/Contact.hh>
#include <gazebo/physics/ContactManager.hh>
#include <gazebo/physics/ode/ODEPhysics.hh>
#include <gazebo/ode/ode.h>
#include <gazebo/physics/Link.hh>
#include <gazebo/physics/Model.hh>
#include <gazebo/physics/PhysicsEngine.hh>
#include <gazebo/physics/World.hh>
#include <sdf/sdf.hh>
#include <nlohmann/json.hpp>
#include <boost/any.hpp>
#include <algorithm>
#include <chrono>
#include <cctype>
#include <cmath>
#include <unistd.h>
#include <cstdio>
#include <dlfcn.h>
#include <filesystem>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#ifndef MR3_OBSERVER_SOURCE_SHA256
#define MR3_OBSERVER_SOURCE_SHA256 "unconfigured_candidate_not_native_credit"
#endif

namespace mr3_diagnostics
{
namespace
{
using Json = nlohmann::json;
void LibraryAnchor() {}

int64_t Ns(const gazebo::common::Time & time)
{
  return static_cast<int64_t>(time.sec) * 1000000000LL + time.nsec;
}

Json Vector(const ignition::math::Vector3d & v)
{
  return {v.X(), v.Y(), v.Z()};
}

Json Pose(const ignition::math::Pose3d & p)
{
  return {{"position_xyz", Vector(p.Pos())},
    {"quaternion_wxyz", {p.Rot().W(), p.Rot().X(), p.Rot().Y(), p.Rot().Z()}}};
}

Json Link(const gazebo::physics::LinkPtr & link)
{
  return {{"name", link->GetScopedName()}, {"world_pose", Pose(link->WorldPose())},
    {"world_cog_pose", Pose(link->WorldCoGPose())},
    {"world_origin_linear_velocity_xyz", Vector(link->WorldLinearVel())},
    {"world_cog_linear_velocity_xyz", Vector(link->WorldCoGLinearVel())},
    {"world_angular_velocity_xyz", Vector(link->WorldAngularVel())}};
}

int64_t ReadNanoseconds(const sdf::ElementPtr & sdf, const std::string & key)
{
  if (!sdf->HasElement(key)) {throw std::invalid_argument("diagnostic ns field missing");}
  const auto text = sdf->Get<std::string>(key);
  if (text.empty() || !std::all_of(text.begin(), text.end(), [](unsigned char ch) {
      return std::isdigit(ch) != 0;
    }))
  {throw std::invalid_argument("diagnostic ns must be a nonnegative decimal integer");}
  return std::stoll(text);
}

Json Parameter(const gazebo::physics::PhysicsEnginePtr & physics, const std::string & key)
{
  boost::any value;
  if (!physics->GetParam(key, value)) {
    return {{"available", false}};
  }
  Json result{{"available", true}, {"cpp_type", value.type().name()},
    {"readback_scope", "public_GetParam_not_independent_native_readback"}};
  if (key == "solver_type" || key == "iters" || key == "sor" || key == "cfm" || key == "erp") {
    result["readback_scope"] = "sdf_cached_public_GetParam";
  }
  if (const auto p = boost::any_cast<double>(&value)) {
    if (!std::isfinite(*p)) {
      return {{"available", false}, {"nonfinite", true},
        {"readback_scope", result["readback_scope"]},
        {"nonfinite_class", std::isnan(*p) ? "NaN" : (*p < 0 ? "-Inf" : "+Inf")}};
    }
    result["value"] = *p;
  }
  else if (const auto p = boost::any_cast<int>(&value)) {result["value"] = *p;}
  else if (const auto p = boost::any_cast<unsigned int>(&value)) {result["value"] = *p;}
  else if (const auto p = boost::any_cast<bool>(&value)) {result["value"] = *p;}
  else if (const auto p = boost::any_cast<std::string>(&value)) {result["value"] = *p;}
  else {result["available"] = false; result["unsupported_return_type"] = true;}
  return result;
}

bool Finite(const Json & value)
{
  if (value.is_number_float() && !std::isfinite(value.get<double>())) {return false;}
  if (value.is_structured()) {
    for (const auto & item : value) {if (!Finite(item)) {return false;}}
  }
  return true;
}

Json NativeOde(const gazebo::physics::PhysicsEnginePtr & physics)
{
  const auto ode = boost::dynamic_pointer_cast<gazebo::physics::ODEPhysics>(physics);
  if (!ode || !ode->GetWorldId()) {
    return {{"available", false}, {"reason", "public_ODE_world_id_unavailable"}};
  }
  const auto id = ode->GetWorldId();
  dVector3 gravity;
  dWorldGetGravity(id, gravity);
  Json values{{"iters", dWorldGetQuickStepNumIterations(id)},
    {"precon_iters", dWorldGetQuickStepPreconIterations(id)},
    {"sor", dWorldGetQuickStepW(id)}, {"cfm", dWorldGetCFM(id)}, {"erp", dWorldGetERP(id)},
    {"contact_max_correcting_vel", dWorldGetContactMaxCorrectingVel(id)},
    {"contact_surface_layer", dWorldGetContactSurfaceLayer(id)},
    {"sor_lcp_tolerance", dWorldGetQuickStepTolerance(id)},
    {"use_dynamic_moi_rescaling", dWorldGetQuickStepInertiaRatioReduction(id)},
    {"gravity_xyz", {gravity[0], gravity[1], gravity[2]}}};
  const bool finite = Finite(values);
  return {{"available", finite}, {"nonfinite", !finite}, {"values", values},
    {"readback_scope", "native_dWorld_getters_on_public_ODEPhysics_GetWorldId"},
    {"solver_dispatch", {{"available", false},
        {"reason", "active_private_step_function_has_no_public_getter; GetStepType_reads_SDF"}}}};
}

Json Contacts(const gazebo::physics::PhysicsEnginePtr & physics,
  const gazebo::physics::ModelPtr & model, int64_t clock_ns, bool solved)
{
  const auto manager = physics->GetContactManager();
  if (!manager) {return {{"available", false}, {"reason", "contact_manager_unavailable"}};}
  const auto count = manager->GetContactCount();
  const auto & all = manager->GetContacts();
  Json result{{"manager_available", true}, {"valid_prefix_count", count},
    {"never_drop_contacts", manager->NeverDropContacts()}, {"records", Json::array()},
    {"scope", "retained_current_own_model_vs_static_environment_support_candidates_only; empty_is_not_no_contact"}};
  if (count > all.size()) {
    result["available"] = false;
    result["reason"] = "valid_prefix_count_exceeds_storage";
    return result;
  }
  // The vector may hold stale capacity beyond GetContactCount(). Never read it.
  for (unsigned int index = 0; index < count; ++index) {
    const auto contact = all[index];
    if (!contact || !contact->collision1 || !contact->collision2) {continue;}
    const auto one = contact->collision1->GetLink();
    const auto two = contact->collision2->GetLink();
    if (!one || !two) {continue;}
    const auto model_one = one->GetModel();
    const auto model_two = two->GetModel();
    const bool own_one = model_one == model;
    const bool own_two = model_two == model;
    if (own_one == own_two) {continue;}
    const auto other = own_one ? model_two : model_one;
    if (!other || !other->IsStatic()) {continue;}
    Json record{{"valid_prefix_index", index},
      {"collision1", contact->collision1->GetScopedName()},
      {"collision2", contact->collision2->GetScopedName()},
      {"link1", one->GetScopedName()}, {"link2", two->GetScopedName()},
      {"own_collision_index", own_one ? 1 : 2}, {"other_model_static", true},
      {"contact_time_ns", Ns(contact->time)}, {"point_count", contact->count},
      {"points", Json::array()}};
    if (Ns(contact->time) != clock_ns || contact->count < 0 || contact->count > MAX_CONTACT_JOINTS) {
      record["available"] = false;
      record["reason"] = "stale_contact_or_invalid_point_count";
      result["records"].push_back(record);
      continue;
    }
    record["available"] = contact->count > 0;
    for (int point = 0; point < contact->count; ++point) {
      Json value{{"position_world_xyz", Vector(contact->positions[point])},
        {"normal_world_xyz", Vector(contact->normals[point])},
        {"depth_m", contact->depths[point]}};
      if (solved && model->GetWorld()->PhysicsEnabled() && physics->GetType() == "ode") {
        const auto & wrench = contact->wrench[point];
        value["forces"] = {{"available", true},
          {"body1_force_link_xyz", Vector(wrench.body1Force)},
          {"body2_force_link_xyz", Vector(wrench.body2Force)},
          {"body1_torque_link_xyz", Vector(wrench.body1Torque)},
          {"body2_torque_link_xyz", Vector(wrench.body2Torque)},
          {"scope", "ODEPhysics_UpdatePhysics_rotates_feedback_into_each_link_frame; torque_about_CoG"}};
      } else {
        value["forces"] = {{"available", false}, {"reason", "current_ODE_solve_not_available_at_this_phase_or_physics_disabled"}};
      }
      record["points"].push_back(value);
    }
    result["records"].push_back(record);
  }
  result["available"] = false;
  for (const auto & record : result["records"]) {
    if (record.value("available", false)) {result["available"] = true;}
  }
  if (!result["available"].get<bool>()) {
    result["reason"] = "no_retained_fresh_own_static_contact_evidence_not_proof_of_no_physical_contact";
  }
  return result;
}
}  // namespace

class State
{
public:
  gazebo::physics::ModelPtr model;
  gazebo::physics::LinkPtr canonical;
  gazebo::physics::LinkPtr base;
  std::vector<gazebo::physics::JointPtr> joints;
  gazebo::event::ConnectionPtr before;
  gazebo::event::ConnectionPtr after;
  std::unique_ptr<std::FILE, decltype(&std::fclose)> output{nullptr, &std::fclose};
  std::string epoch;
  std::string robot;
  int64_t start_ns{0};
  int64_t end_ns{0};
  int64_t pair_clock_ns{0};
  uint64_t sequence{0};
  uint64_t pair_sequence{0};
  uint64_t pair_iterations{0};
  uint64_t before_record_sequence{0};
  bool pair_active{false};
  bool capture_complete{false};
  bool paused_only{false};

  // These callbacks run on the world's physics-update thread. They never
  // publish ROS/Gazebo messages, call setters, or access another robot.
  void Write(const char * kind, int64_t clock_ns, Json row)
  {
    row.update({{"schema", "mr3-stop-response-observer-v1"}, {"kind", kind},
      {"epoch", epoch}, {"robot", robot}, {"record_sequence", ++sequence},
      {"sim_time_ns", clock_ns}, {"world_iterations", model->GetWorld()->Iterations()},
      {"wall_monotonic_ns", std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now().time_since_epoch()).count()}});
    row["measurements_finite"] = Finite(row);
    const auto bytes = row.dump() + "\n";
    // Buffered stdio avoids a per-row fsync/fflush burden. Every completed
    // post-physics pair is flushed; any write failure invalidates the run.
    if (std::fwrite(bytes.data(), 1, bytes.size(), output.get()) != bytes.size()) {
      throw std::runtime_error("cannot write stop-response diagnostic");
    }
  }

  void Sample(const char * phase, int64_t clock_ns)
  {
    const auto physics = model->GetWorld()->Physics();
    Json solver;
    for (const auto & key : {"rms_error", "constraint_residual", "num_contacts"}) {
      solver[key] = Parameter(physics, key);
    }
    Json wheel = Json::array();
    for (const auto & joint : joints) {
      wheel.push_back({{"name", joint->GetScopedName()},
        {"position_rad", joint->Position(0)}, {"velocity_radps", joint->GetVelocity(0)},
        {"motor_velocity_target_radps", joint->GetParam("vel", 0)},
        {"motor_fmax_nm", joint->GetParam("fmax", 0)},
        {"axis_get_force_nm", joint->GetForce(0)}});
    }
    Write("sample", clock_ns, {{"phase", phase}, {"pair_sequence", pair_sequence},
      {"physics_enabled", model->GetWorld()->PhysicsEnabled()},
      {"before_record_sequence", before_record_sequence}, {"pair_iterations", pair_iterations},
      {"before_clock_ns", pair_clock_ns},
      {"model", {{"name", model->GetScopedName()}, {"world_pose", Pose(model->WorldPose())},
          {"world_linear_velocity_xyz", Vector(model->WorldLinearVel())},
          {"world_angular_velocity_xyz", Vector(model->WorldAngularVel())}}},
      {"canonical", Link(canonical)}, {"base", Link(base)}, {"joints_right_left", wheel},
      {"solver_diagnostics_world_scope", solver},
      {"native_ode", NativeOde(physics)},
      {"contacts", Contacts(physics, model, clock_ns,
          std::string(phase) == "world_update_end_after_physics_and_pose_propagation")},
      {"scope", "read_only_physics_getters; motor target is GetParam(vel), not private driver desired or actuator feedback ACK"}});
  }

  void Before(const gazebo::common::UpdateInfo & info)
  {
    if (capture_complete) {return;}
    if (pair_active) {
      throw std::runtime_error("diagnostic prior physics pair not closed");
    }
    const auto clock_ns = Ns(info.simTime);
    // V2 fixtures observe only real paused World::Step calls. Startup remains
    // untouched; this is a read-only selection, not a pause/physics setter.
    if (paused_only && !model->GetWorld()->IsPaused()) {return;}
    if (clock_ns < start_ns) {return;}
    if (clock_ns > end_ns) {
      if (!capture_complete) {
        Write("capture_complete", clock_ns, {{"last_pair_sequence", pair_sequence}});
        if (std::fflush(output.get()) != 0) {throw std::runtime_error("diagnostic flush failed");}
        capture_complete = true;
      }
      return;
    }
    pair_active = true;
    pair_clock_ns = clock_ns;
    pair_iterations = model->GetWorld()->Iterations();
    ++pair_sequence;
    before_record_sequence = sequence + 1;
    Sample("before_physics_after_collision", clock_ns);
  }

  void After()
  {
    if (!pair_active) {return;}
    const auto clock_ns = Ns(model->GetWorld()->SimTime());
    if (clock_ns != pair_clock_ns || model->GetWorld()->Iterations() != pair_iterations) {
      throw std::runtime_error("diagnostic pre/post physics world-clock or iteration mismatch");
    }
    Sample("world_update_end_after_physics_and_pose_propagation", clock_ns);
    pair_active = false;
    if (std::fflush(output.get()) != 0) {throw std::runtime_error("diagnostic flush failed");}
  }
};

class StopResponseObserver : public gazebo::ModelPlugin
{
public:
  ~StopResponseObserver() override
  {
    // Disconnect future weak callbacks. An in-flight callback owns State until
    // it returns, so its FILE/model pointers cannot be destroyed mid-read.
    auto state = std::move(state_);
    if (state) {state->before.reset(); state->after.reset();}
  }

  void Load(gazebo::physics::ModelPtr model, sdf::ElementPtr sdf) override
  {
    auto state = std::make_shared<State>();
    state->model = model;
    state->epoch = sdf->Get<std::string>("epoch", "").first;
    state->robot = sdf->Get<std::string>("robot", "").first;
    state->start_ns = ReadNanoseconds(sdf, "start_ns");
    state->end_ns = ReadNanoseconds(sdf, "end_ns");
    state->paused_only = sdf->Get<bool>("paused_only", false).first;
    const auto path = sdf->Get<std::string>("output_path", "").first;
    if (state->epoch.empty() || state->robot.empty() || path.empty() ||
      state->start_ns < 0 || state->end_ns <= state->start_ns)
    {
      throw std::invalid_argument("diagnostic requires epoch/robot/exclusive output and finite increasing window");
    }
    // Names are explicitly taken from the same effective diagnostic SDF and
    // must be verified against its unchanged original driver plugin by admission.
    const auto base_name = sdf->Get<std::string>("base_link", "").first;
    if (base_name.empty()) {throw std::invalid_argument("diagnostic base_link must be explicit");}
    state->canonical = model->GetLink();
    state->base = model->GetLink(base_name);
    for (const auto & tag : {"right_joint", "left_joint"}) {
      auto joint = model->GetJoint(sdf->Get<std::string>(tag, "").first);
      if (!joint) {throw std::invalid_argument("diagnostic wheel joint missing");}
      state->joints.push_back(joint);
    }
    if (!state->canonical || !state->base) {throw std::invalid_argument("diagnostic body link missing");}
    const auto parent = std::filesystem::path(path).parent_path();
    if (!parent.empty()) {std::filesystem::create_directories(parent);}
    state->output.reset(std::fopen(path.c_str(), "wx"));
    if (!state->output) {throw std::runtime_error("cannot exclusively create diagnostic output");}
    auto physics = model->GetWorld()->Physics();
    Json params;
    for (const auto & key : {"solver_type", "cfm", "erp", "precon_iters", "iters", "sor",
      "contact_max_correcting_vel", "contact_surface_layer", "max_contacts", "max_step_size",
      "sor_lcp_tolerance", "use_dynamic_moi_rescaling", "friction_model", "world_step_solver"})
    {params[key] = Parameter(physics, key);}
    Dl_info loaded{};
    std::string library;
    if (dladdr(reinterpret_cast<void *>(&LibraryAnchor), &loaded) && loaded.dli_fname) {
      library = std::filesystem::canonical(loaded.dli_fname).string();
    }
    state->Write("configuration", Ns(model->GetWorld()->SimTime()), {
      {"loaded_library_path", library}, {"compiled_source_sha256", MR3_OBSERVER_SOURCE_SHA256},
      {"process_id", static_cast<int64_t>(::getpid())},
      {"world_name", model->GetWorld()->Name()},
      {"native_ode", NativeOde(physics)},
      {"physics_type", physics->GetType()}, {"max_step_size_sec", physics->GetMaxStepSize()},
      {"physics_parameters", params},
      {"physics_parameters_scope", "public_GetParam; solver_type/iters/sor/cfm/erp_are_SDF_cached"},
      {"gravity_xyz", Vector(model->GetWorld()->Gravity())},
      {"start_ns", state->start_ns}, {"end_ns", state->end_ns},
      {"paused_only", state->paused_only},
      {"canonical_name", state->canonical->GetScopedName()}, {"base_name", state->base->GetScopedName()},
      {"read_only", true}, {"per_packet_or_driver_private_sequence", false},
      {"flush_per_completed_pair", true},
      {"observer_effect", "synchronous getter/JSON/stdio wall-time overhead; no setter or transport publisher"},
      {"axis_get_force_scope", "Joint::GetForce readback, not a promised motor/solver reaction wrench"}});
    state->before = gazebo::event::Events::ConnectBeforePhysicsUpdate(
      [weak = std::weak_ptr<State>(state)](const gazebo::common::UpdateInfo & info) {
        if (auto current = weak.lock()) {current->Before(info);}
      });
    state->after = gazebo::event::Events::ConnectWorldUpdateEnd(
      [weak = std::weak_ptr<State>(state)]() {
        if (auto current = weak.lock()) {current->After();}
      });
    state_ = std::move(state);
  }

private:
  std::shared_ptr<State> state_;
};
GZ_REGISTER_MODEL_PLUGIN(StopResponseObserver)
}  // namespace mr3_diagnostics
