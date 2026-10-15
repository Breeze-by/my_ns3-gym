// Explicit paused-physics stepping. This plugin never reads robot poses or maps.
#include <cmath>
#include <mutex>
#include <string>
#include <unordered_map>
#include <gazebo/gazebo.hh>
#include <gazebo/common/Events.hh>
#include <gazebo/msgs/msgs.hh>
#include <gazebo/physics/physics.hh>
#include <gazebo/transport/transport.hh>
#include "multi_robot/mr3_step_contract.hpp"

namespace gazebo {
class MR3GazeboStep : public SystemPlugin {
 public:
  void Load(int, char **) override {
    created_ = event::Events::ConnectWorldCreated(
      std::bind(&MR3GazeboStep::WorldCreated, this, std::placeholders::_1));
  }

 private:
  void WorldCreated(const std::string & name) {
    world_ = physics::get_world(name);
    node_.reset(new transport::Node());
    node_->Init(name);
    replies_ = node_->Advertise<msgs::GzString>("~/mr3_step/response", 100);
    requests_ = node_->Subscribe("~/mr3_step/request", &MR3GazeboStep::Request, this);
  }

  void Request(ConstGzStringPtr & message) {
    mr3::Json response;
    std::lock_guard<std::mutex> guard(mutex_);
    try {
      const auto input = mr3::Json::parse(message->data());
      const auto request = mr3::ParseStepRequest(input);
      response = {{"epoch", request.epoch}, {"request_id", request.request_id}};
      mr3::CheckEpoch(request.epoch, epoch_);
      const auto previous = completed_.find(request.request_id);
      if (previous != completed_.end()) {
        if (previous->second.first != input) {
          throw std::invalid_argument("request_id reused with different physics command");
        }
        Publish(previous->second.second);
        return;
      }
      if (completed_.size() >= 100000) {
        throw std::runtime_error("physics request ledger full; rebuild worker");
      }
      epoch_ = request.epoch;
      world_->SetPaused(true);
      const auto tick_ns = std::llround(world_->Physics()->GetMaxStepSize() * 1e9);
      if (tick_ns != request.step_ns) {
        throw std::runtime_error("world max_step_size differs from frozen physics tick");
      }
      const auto start_ns = world_->SimTime().sec * 1000000000LL + world_->SimTime().nsec;
      const auto start_iterations = world_->Iterations();
      // Gazebo's public Step blocks until exactly this many physics iterations
      // complete. This transport callback is separate from the physics thread.
      world_->Step(request.steps);
      const auto end_ns = world_->SimTime().sec * 1000000000LL + world_->SimTime().nsec;
      const auto end_iterations = world_->Iterations();
      const bool paused = world_->IsPaused();
      const bool exact = mr3::ExactStep(start_ns, end_ns, start_iterations,
        end_iterations, request.steps, tick_ns, paused);
      response.update({{"ok", exact}, {"start_time_ns", start_ns}, {"end_time_ns", end_ns},
        {"start_iterations", start_iterations}, {"end_iterations", end_iterations},
        {"steps", request.steps}, {"step_ns", tick_ns}, {"paused", paused}});
      if (!exact) {
        response["error"] = "physics iteration/time mismatch";
      }
      completed_.emplace(request.request_id, std::make_pair(input, response));
    } catch (const std::exception & error) {
      response.update({{"ok", false}, {"error", error.what()}});
    }
    Publish(response);
  }

  void Publish(const mr3::Json & response) {
    msgs::GzString message;
    message.set_data(response.dump());
    replies_->Publish(message);
  }

  std::string epoch_;
  std::mutex mutex_;
  physics::WorldPtr world_;
  transport::NodePtr node_;
  transport::PublisherPtr replies_;
  transport::SubscriberPtr requests_;
  event::ConnectionPtr created_;
  std::unordered_map<std::string, std::pair<mr3::Json, mr3::Json>> completed_;
};
GZ_REGISTER_SYSTEM_PLUGIN(MR3GazeboStep)
}  // namespace gazebo
