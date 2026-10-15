// JSONL frontend for the owned Gazebo stepping plugin. No ROS Python dependency.
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <iostream>
#include <mutex>
#include <string>
#include <gazebo/gazebo_client.hh>
#include <gazebo/msgs/msgs.hh>
#include <gazebo/transport/transport.hh>
#include "multi_robot/mr3_step_contract.hpp"

class StepClient {
 public:
  StepClient(const std::string & world, double timeout) : timeout_(timeout) {
    node_.reset(new gazebo::transport::Node());
    node_->Init(world);
    subscriber_ = node_->Subscribe("~/mr3_step/response", &StepClient::Reply, this);
    publisher_ = node_->Advertise<gazebo::msgs::GzString>("~/mr3_step/request", 100);
    if (!publisher_->WaitForConnection(gazebo::common::Time(timeout))) {
      throw std::runtime_error("owned stepping plugin is unavailable");
    }
  }

  mr3::Json Step(const mr3::Json & input) {
    const auto request = mr3::ParseStepRequest(input);
    {
      std::lock_guard<std::mutex> lock(mutex_);
      expected_ = request.request_id;
      response_ = nullptr;
    }
    gazebo::msgs::GzString message;
    message.set_data(input.dump());
    publisher_->Publish(message, true);
    std::unique_lock<std::mutex> lock(mutex_);
    if (!condition_.wait_for(lock, std::chrono::duration<double>(timeout_),
      [this] {return !response_.is_null();})) {
      throw std::runtime_error("physics request timed out; ownership unknown, rebuild worker");
    }
    if (response_.value("epoch", "") != request.epoch) {
      throw std::runtime_error("cross-epoch physics reply");
    }
    if (response_.value("ok", false) && !mr3::ExactStep(
      response_.at("start_time_ns"), response_.at("end_time_ns"),
      response_.at("start_iterations"), response_.at("end_iterations"),
      request.steps, request.step_ns, response_.at("paused"))) {
      throw std::runtime_error("invalid exact-step receipt");
    }
    return response_;
  }

 private:
  void Reply(const boost::shared_ptr<const gazebo::msgs::GzString> & message) {
    try {
      auto response = mr3::Json::parse(message->data());
      std::lock_guard<std::mutex> lock(mutex_);
      if (response.value("request_id", "") == expected_) {
        response_ = response;
        condition_.notify_one();
      }
    } catch (const std::exception &) {
      // An unrelated malformed transport message cannot satisfy our request.
    }
  }

  double timeout_;
  std::string expected_;
  mr3::Json response_;
  std::mutex mutex_;
  std::condition_variable condition_;
  gazebo::transport::NodePtr node_;
  gazebo::transport::PublisherPtr publisher_;
  gazebo::transport::SubscriberPtr subscriber_;
};

int main(int argc, char ** argv) {
  std::string world = "default", epoch = "mr3-step";
  bool jsonl = false;
  int steps = 0;
  double timeout = 10.;
  try {
    for (int i = 1; i < argc; ++i) {
      const std::string flag(argv[i]);
      if (flag == "--jsonl") {jsonl = true; continue;}
      if (i + 1 >= argc) {throw std::invalid_argument("missing CLI value");}
      const std::string value(argv[++i]);
      if (flag == "--world") {world = value;}
      else if (flag == "--epoch") {epoch = value;}
      else if (flag == "--steps") {steps = std::stoi(value);}
      else if (flag == "--timeout-sec") {timeout = std::stod(value);}
      else {throw std::invalid_argument("unknown CLI argument");}
    }
    if (!std::isfinite(timeout) || timeout <= 0) {throw std::invalid_argument("invalid timeout");}
    gazebo::client::setup();
    {
      StepClient client(world, timeout);
      std::string line;
      unsigned int sequence = 0;
      do {
        if (jsonl && !std::getline(std::cin, line)) {break;}
        auto input = jsonl ? mr3::Json::parse(line) : mr3::Json{{"steps", steps}};
        if (!input.contains("epoch")) {input["epoch"] = epoch;}
        if (!input.contains("request_id")) {
          input["request_id"] = epoch + ":" + std::to_string(++sequence);
        }
        const auto response = client.Step(input);
        std::cout << response.dump() << std::endl;
        if (!response.value("ok", false)) {gazebo::client::shutdown(); return 1;}
      } while (jsonl);
    }
    gazebo::client::shutdown();
    return 0;
  } catch (const std::exception & error) {
    std::cout << mr3::Json{{"ok", false}, {"error", error.what()}}.dump() << std::endl;
    gazebo::client::shutdown();
    return 1;
  }
}
