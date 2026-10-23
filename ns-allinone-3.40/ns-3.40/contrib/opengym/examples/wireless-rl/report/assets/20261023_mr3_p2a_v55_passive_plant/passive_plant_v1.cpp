// Disabled standalone Gazebo 11 plant diagnostic, not an MR3 environment.
// Only joint fmax/velocity motor parameters are written. No pose/body velocity,
// joint position, fixed-joint, or anchor refresh operation is performed.
#include <gazebo/gazebo.hh>
#include <gazebo/common/Events.hh>
#include <gazebo/physics/physics.hh>
#include <gazebo/physics/ContactManager.hh>
#include <gazebo/physics/Contact.hh>
#include <gazebo/physics/ode/ODEPhysics.hh>
#include <ignition/math/Rand.hh>
#include <multi_robot/paired_wheel_slew.hpp>
#include <nlohmann/json.hpp>
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <stdexcept>
#include <sstream>
#include <string>
#include <unistd.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <vector>

using Json = nlohmann::json;
namespace fs = std::filesystem;
using Clock = std::chrono::steady_clock;
static volatile std::sig_atomic_t interrupted = 0;
static void signal_received(int value) { interrupted = value; }
static void require(bool value, const std::string & why) {
  if (!value) throw std::runtime_error(why);
}
static int64_t ns(const gazebo::common::Time & time) {
  return int64_t(time.sec) * 1000000000 + time.nsec;
}
static double seconds(Clock::time_point start) {
  return std::chrono::duration<double>(Clock::now() - start).count();
}
static void finite(std::initializer_list<double> values) {
  for (double value : values) require(std::isfinite(value), "nonfinite plant observation");
}
static Json identity() {
  std::ifstream stream("/proc/self/stat"); std::string line; std::getline(stream, line);
  auto end = line.rfind(')'); require(end != std::string::npos, "self stat unavailable");
  std::istringstream fields(line.substr(end + 2)); std::string token;
  for (int field = 3; field <= 22; ++field) {
    require(bool(fields >> token), "self start_ticks unavailable");
  }
  return {{"pid", getpid()}, {"parent", getppid()}, {"group", getpgrp()},
          {"session", getsid(0)}, {"start_ticks", std::stoll(token)}};
}
static Json loaded_libraries() {
  std::ifstream stream("/proc/self/maps"); std::string line; std::map<std::string, bool> paths;
  while (std::getline(stream, line)) {
    auto slash = line.find('/'); if (slash == std::string::npos) continue;
    std::string path = line.substr(slash);
    if (path.find("libgazebo") != std::string::npos || path.find("libsdformat") != std::string::npos)
      paths[path] = true;
  }
  Json result = Json::array(); for (const auto & item : paths) result.push_back(item.first);
  return result;
}
static void require_owned_master_port_free() {
  const char * uri = std::getenv("GAZEBO_MASTER_URI");
  require(uri && std::string(uri) == "http://127.0.0.1:11555", "exclusive fixed GAZEBO_MASTER_URI required");
  const int socket_fd = socket(AF_INET, SOCK_STREAM, 0);
  require(socket_fd >= 0, "master port precheck socket failed");
  const int reuse = 1;
  if (setsockopt(socket_fd, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse)) != 0) {
    close(socket_fd); throw std::runtime_error("master port precheck setsockopt failed");
  }
  sockaddr_in address{}; address.sin_family = AF_INET; address.sin_port = htons(11555);
  address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  const bool free = bind(socket_fd, reinterpret_cast<sockaddr *>(&address), sizeof(address)) == 0;
  close(socket_fd); require(free, "master port already in use; no existing master may be reused");
}

struct Robot {
  std::string name;
  gazebo::physics::ModelPtr model;
  std::array<gazebo::physics::JointPtr, 2> joints;  // right, left (production helper order)
  ignition::math::Vector3d anchor, previous;
  Json anchor_pose, first_exceeded = nullptr;
  double maximum = 0, chord_sum = 0, max_planar = 0, max_angular = 0;
  double max_wheel_speed = 0, max_wheel_angle_delta = 0;
  std::array<double, 2> anchor_angles{}, commanded{};
  uint64_t motor_updates = 0, observed_steps = 0;
};

int main(int argc, char ** argv) {
  const auto entered = Clock::now();
  Json result = {{"schema", "mr3-v55-passive-plant-result-v1"},
    {"execution_passed", false}, {"qualification", false}, {"errors", Json::array()},
    {"desired_body_target", {0.0, 0.0}}, {"desired_wheel_rim_target", {0.0, 0.0}},
    {"fixed_anchor_radius_m", 0.0078}, {"settle_seconds", 45}, {"hold_seconds", 310},
    {"physics_step_ns", 1000000}, {"motor_update_period_ns", 34000000},
    {"motor_policy", "production paired feedback slew: desired0,accel1,torque20,radius.033"}};
  gazebo::physics::WorldPtr world;
  gazebo::event::ConnectionPtr begin, end;
  fs::path output; std::ofstream samples;
  bool server = false, server_attempted = false, anchor_set = false, owns_output = false;
  std::vector<Robot> robots; uint64_t end_calls = 0, contact_observations = 0;
  std::map<std::string, uint64_t> contact_pairs;
  int64_t first_end = -1, previous_end = -1, last_actuation = 0;
  gazebo::common::Time last_update_time;
  std::string callback_error;
  try {
    require(argc == 9, "expected --arm ARM --world WORLD --output NEWDIR --work-seconds 600");
    std::map<std::string, std::string> options;
    for (int i = 1; i < argc; i += 2) require(options.emplace(argv[i], argv[i+1]).second, "duplicate option");
    require(options.size() == 4 && options.count("--arm") && options.count("--world") &&
      options.count("--output") && options.count("--work-seconds"), "unexpected option");
    const std::string arm = options.at("--arm");
    require(arm == "quick50" || arm == "direct-world", "unregistered arm");
    require(options.at("--work-seconds") == "600", "work cap must be exactly600");
    output = options.at("--output"); require(output.is_absolute(), "absolute exclusive output required");
    require(fs::is_regular_file(options.at("--world")), "world regular file required");
    require(fs::create_directory(output), "output already exists");
    owns_output = true;
    result["identity"] = identity(); result["arm"] = arm;
    result["actual_argv"] = Json::array(); for (int i = 0; i < argc; ++i) result["actual_argv"].push_back(argv[i]);
    { std::ofstream entry(output / "identity.json");
      entry << Json({{"identity", result["identity"]}, {"actual_argv", result["actual_argv"]}}).dump(2) << '\n';
      entry.flush(); require(bool(entry), "early identity write failed"); }
    result["world"] = fs::absolute(options.at("--world")).string();
    std::signal(SIGTERM, signal_received); std::signal(SIGINT, signal_received);
    require_owned_master_port_free(); result["gazebo_master_uri"] = "http://127.0.0.1:11555";
    server_attempted = true; server = gazebo::setupServer(); require(server, "setupServer failed");
    std::signal(SIGTERM, signal_received); std::signal(SIGINT, signal_received);
    ignition::math::Rand::Seed(101);
    require(ignition::math::Rand::Seed() == 101, "native random seed readback differs");
    result["native_seed_api"] = "ignition::math::Rand::Seed"; result["native_seed"] = ignition::math::Rand::Seed();
    world = gazebo::loadWorld(options.at("--world")); require(bool(world), "loadWorld failed");
    auto physics = world->Physics(); require(bool(physics), "no physics engine");
    physics->SetSeed(101);
    result["physics_seed_api"] = "gazebo::physics::PhysicsEngine::SetSeed";
    result["physics_seed_set_call_completed"] = true;
    result["physics_seed_readback_claimed"] = false;
    auto ode = boost::dynamic_pointer_cast<gazebo::physics::ODEPhysics>(physics);
    require(bool(ode), "physics engine is not native ODEPhysics");
    const auto solver = ode->GetStepType(); const int iterations = ode->GetSORPGSIters();
    Json parameters = {{"engine", physics->GetType()}, {"solver_type", solver}, {"iters", iterations},
      {"max_step_size", physics->GetMaxStepSize()}, {"real_time_update_rate", physics->GetRealTimeUpdateRate()}};
    parameters.update({{"sor", ode->GetSORPGSW()}, {"cfm", ode->GetWorldCFM()}, {"erp", ode->GetWorldERP()},
      {"contact_max_correcting_vel", ode->GetContactMaxCorrectingVel()},
      {"contact_surface_layer", ode->GetContactSurfaceLayer()}, {"friction_model", ode->GetFrictionModel()},
      {"world_step_solver", ode->GetWorldStepSolverType()}});
    result["actual_physics_parameters"] = parameters;
    result["parameter_readback_scope"] = "native ODEPhysics/PhysicsEngine getters; not convergence proof; world ignores quick iterations";
    require(physics->GetType() == "ode" && solver == (arm == "quick50" ? "quick" : "world") &&
      (arm != "quick50" || iterations == 50) && physics->GetMaxStepSize() == .001 &&
      physics->GetRealTimeUpdateRate() == 0, "actual solver/step/update parameters differ");
    const auto gravity = world->Gravity();
    require(gravity.X() == 0 && gravity.Y() == 0 && gravity.Z() == -9.8, "gravity differs");
    result["gravity"] = {gravity.X(), gravity.Y(), gravity.Z()};
    require(ns(world->SimTime()) == 0, "world did not start at zero");
    require(world->Models().size() == 4, "expected only ground and three bodies");
    for (const std::string name : {"tb1", "tb2", "tb3"}) {
      Robot item; item.name = name; item.model = world->ModelByName(name);
      require(bool(item.model), "missing canonical body: " + name);
      item.joints = {item.model->GetJoint("wheel_right_joint"), item.model->GetJoint("wheel_left_joint")};
      for (auto joint : item.joints) {
        require(bool(joint), "missing wheel joint");
        require(joint->SetParam("fmax", 0, 20.0), "wheel fmax write failed");
        require(joint->GetParam("fmax", 0) == 20.0, "wheel torque readback differs");
      }
      robots.push_back(item);
    }
    // Observer registration requests retention only; it does not alter contacts or forces.
    physics->GetContactManager()->SetNeverDropContacts(true);
    samples.open(output / "samples.csv"); require(bool(samples), "samples open failed");
    samples << "sim_ns,robot,x,y,z,qw,qx,qy,qz,vx,vy,vz,wx,wy,wz,right_position,left_position,right_velocity,left_velocity,right_command,left_command,anchor_displacement_m\n";
    samples << std::setprecision(17);
    begin = gazebo::event::Events::ConnectWorldUpdateBegin([&](const gazebo::common::UpdateInfo & info) {
      if (!callback_error.empty()) return;
      try {
        const int64_t now = ns(info.simTime);
        const double dt = (info.simTime - last_update_time).Double();
        if (dt < 1.0/30.0) return;
        require(now - last_actuation == 34000000, "actuation was not actual34ms");
        for (auto & item : robots) {
          const std::array<double, 2> current{item.joints[0]->GetVelocity(0)*.033, item.joints[1]->GetVelocity(0)*.033};
          const auto limited = multi_robot::limit_paired_wheel_speeds(current, {0.0, 0.0}, 1.0, dt);
          for (unsigned i = 0; i < 2; ++i) {
            item.commanded[i] = limited.applied[i] / .033;
            require(item.joints[i]->SetParam("vel", 0, item.commanded[i]), "wheel velocity motor write failed");
          }
          ++item.motor_updates;
        }
        last_actuation = now;
        last_update_time = info.simTime;
      } catch (const std::exception & error) { callback_error = error.what(); world->Stop(); }
    });
    end = gazebo::event::Events::ConnectWorldUpdateEnd([&]() {
      if (!callback_error.empty()) return;
      try {
        const int64_t now = ns(world->SimTime()); ++end_calls;
        if (end_calls == 1) first_end = now;
        require(end_calls != 1 || now == 1000000, "first UpdateEnd clock was not1ms");
        require(previous_end < 0 || now - previous_end == 1000000, "noncontinuous1ms observations");
        previous_end = now;
        if (interrupted || seconds(entered) > 600) { world->Stop(); return; }
        if (!anchor_set && now >= 45000000000LL) {
          require(now == 45000000000LL, "settle anchor missed");
          for (auto & item : robots) {
            const auto pose = item.model->WorldPose(); item.anchor = item.previous = pose.Pos();
            item.anchor_pose = {pose.Pos().X(), pose.Pos().Y(), pose.Pos().Z(), pose.Rot().W(), pose.Rot().X(), pose.Rot().Y(), pose.Rot().Z()};
            for (unsigned i = 0; i < 2; ++i) item.anchor_angles[i] = item.joints[i]->Position(0);
          }
          anchor_set = true;
        }
        auto manager = physics->GetContactManager();
        const auto & contacts = manager->GetContacts();
        for (unsigned i = 0; i < manager->GetContactCount(); ++i) {
          auto contact = contacts.at(i); require(contact && contact->collision1 && contact->collision2, "invalid contact record");
          std::string a = contact->collision1->GetScopedName(), b = contact->collision2->GetScopedName();
          if (b < a) std::swap(a, b); ++contact_pairs[a + " | " + b]; ++contact_observations;
          require(contact_pairs.size() <= 256, "unexpected contact pair count");
        }
        if (!anchor_set) return;
        for (auto & item : robots) {
          const auto pose = item.model->WorldPose(); const auto xyz = pose.Pos();
          const auto v = item.model->WorldLinearVel(), w = item.model->WorldAngularVel();
          finite({xyz.X(), xyz.Y(), xyz.Z(), v.X(), v.Y(), v.Z(), w.X(), w.Y(), w.Z(),
            pose.Rot().W(), pose.Rot().X(), pose.Rot().Y(), pose.Rot().Z()});
          const double displacement = std::hypot(xyz.X()-item.anchor.X(), xyz.Y()-item.anchor.Y());
          item.maximum = std::max(item.maximum, displacement);
          item.chord_sum += std::hypot(xyz.X()-item.previous.X(), xyz.Y()-item.previous.Y());
          item.previous = xyz; ++item.observed_steps;
          item.max_planar = std::max(item.max_planar, std::hypot(v.X(), v.Y()));
          item.max_angular = std::max(item.max_angular, w.Length());
          if (displacement > .0078 && item.first_exceeded.is_null()) item.first_exceeded = now;
          std::array<double, 2> q{}, velocity{};
          for (unsigned i = 0; i < 2; ++i) {
            q[i] = item.joints[i]->Position(0); velocity[i] = item.joints[i]->GetVelocity(0);
            finite({q[i], velocity[i]});
            item.max_wheel_speed = std::max(item.max_wheel_speed, std::abs(velocity[i]));
            item.max_wheel_angle_delta = std::max(item.max_wheel_angle_delta, std::abs(q[i]-item.anchor_angles[i]));
          }
          if (now % 20000000 == 0) samples << now << ',' << item.name << ',' << xyz.X() << ',' << xyz.Y() << ',' << xyz.Z()
            << ',' << pose.Rot().W() << ',' << pose.Rot().X() << ',' << pose.Rot().Y() << ',' << pose.Rot().Z()
            << ',' << v.X() << ',' << v.Y() << ',' << v.Z() << ',' << w.X() << ',' << w.Y() << ',' << w.Z()
            << ',' << q[0] << ',' << q[1] << ',' << velocity[0] << ',' << velocity[1]
            << ',' << item.commanded[0] << ',' << item.commanded[1] << ',' << displacement << '\n';
        }
        require(bool(samples), "sample write failed");
      } catch (const std::exception & error) { callback_error = error.what(); world->Stop(); }
    });
    gazebo::runWorld(world, 355000);
    result["loaded_library_paths"] = loaded_libraries();
    result["completed_sim_ns"] = ns(world->SimTime()); result["update_end_calls"] = end_calls;
    result["actual_step_count"] = world->Iterations();
    require(callback_error.empty(), "callback failed: " + callback_error);
    require(!interrupted && seconds(entered) <= 600, "interrupted or exceeded cooperative600s cap");
    require(anchor_set && first_end == 1000000 && previous_end == 355000000000LL &&
      ns(world->SimTime()) == 355000000000LL && end_calls == 355000 && world->Iterations() == 355000,
      "incomplete355s native execution");
    for (const auto & item : robots) require(item.observed_steps == 310001, "incomplete post-anchor observations");
    result["execution_passed"] = true;
  } catch (const std::exception & error) { result["errors"].push_back(error.what()); }
  begin.reset(); end.reset();
  result["robots"] = Json::array();
  for (const auto & item : robots) result["robots"].push_back({{"robot", item.name},
    {"anchor_pose", item.anchor_pose}, {"anchor_clock_ns", anchor_set ? Json(45000000000LL) : Json(nullptr)},
    {"maximum_anchor_displacement_m", item.maximum}, {"first_radius_exceeded_clock_ns", item.first_exceeded},
    {"within_R_observed", anchor_set ? Json(item.maximum <= .0078) : Json(nullptr)},
    {"sampled_planar_chord_sum_m", item.chord_sum}, {"maximum_planar_speed_mps", item.max_planar},
    {"maximum_angular_norm_radps", item.max_angular}, {"maximum_abs_wheel_speed_radps", item.max_wheel_speed},
    {"maximum_abs_wheel_angle_change_rad", item.max_wheel_angle_delta}, {"post_anchor_observations", item.observed_steps},
    {"motor_updates", item.motor_updates}});
  result["update_end_calls"] = end_calls;
  result["first_update_end_clock_ns"] = first_end < 0 ? Json(nullptr) : Json(first_end);
  result["last_update_end_clock_ns"] = previous_end < 0 ? Json(nullptr) : Json(previous_end);
  result["radius_metric_scope"] = "binary64 position/std::hypot sampled at1ms; not exact-Q replay or continuous proof";
  result["contact_count_scope"] = "per-step contact observations; not eighteen-stream unsafe event rate";
  if (world) { result["completed_sim_ns"] = ns(world->SimTime()); result["actual_step_count"] = world->Iterations(); world->Stop(); }
  if (samples.is_open()) { samples.flush(); result["samples_write_ok"] = bool(samples); samples.close(); }
  try { result["gazebo_shutdown_returned"] = server_attempted && gazebo::shutdown(); }
  catch (const std::exception & error) {
    result["gazebo_shutdown_returned"] = false; result["errors"].push_back(std::string("shutdown: ") + error.what());
  }
  result["received_signal"] = int(interrupted); result["contact_pair_counts"] = contact_pairs;
  result["contact_observations"] = contact_observations; result["wall_seconds_to_shutdown"] = seconds(entered);
  result["execution_passed"] = result["execution_passed"].get<bool>() && !interrupted &&
    result.value("samples_write_ok", false) && result.value("gazebo_shutdown_returned", false) && seconds(entered) <= 600;
  result["diagnostic_only"] = "sampled passive fixed-zero plant; no task, actor, continuous proof or qualification";
  result["completion_status"] = result["execution_passed"].get<bool>() ? "COMPLETE" : "PARTIAL_OR_FAIL";
  if (owns_output) {
    std::ofstream receipt(output / "summary.json"); receipt << result.dump(2) << '\n'; receipt.flush();
    if (!receipt) return 1;
  }
  std::cout << Json({{"execution_passed", result["execution_passed"]}, {"output", output.string()},
    {"errors", result["errors"]}}).dump() << '\n';
  return result["execution_passed"].get<bool>() && !interrupted && seconds(entered) <= 600 ? 0 : 1;
}
