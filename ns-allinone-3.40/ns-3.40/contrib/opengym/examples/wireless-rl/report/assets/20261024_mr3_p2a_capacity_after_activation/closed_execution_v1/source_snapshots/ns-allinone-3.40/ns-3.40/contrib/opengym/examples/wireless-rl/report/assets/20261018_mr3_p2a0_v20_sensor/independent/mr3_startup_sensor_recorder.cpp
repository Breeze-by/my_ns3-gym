// Standalone passive sensor capture. --self-test does not initialize ROS/DDS.
#include <rclcpp/rclcpp.hpp>
#include <rclcpp/serialization.hpp>
#include <rclcpp/serialized_message.hpp>
#include <sensor_msgs/msg/laser_scan.hpp>
#include <nav_msgs/msg/occupancy_grid.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <geometry_msgs/msg/pose_with_covariance_stamped.hpp>
#include <tf2_msgs/msg/tf_message.hpp>
#include <rosgraph_msgs/msg/clock.hpp>
#include <rcl_interfaces/srv/list_parameters.hpp>
#include <rcl_interfaces/srv/get_parameters.hpp>
#include <nlohmann/json.hpp>
#include <openssl/sha.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <array>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <vector>

#ifndef MR3_RECORDER_SOURCE_SHA256
#define MR3_RECORDER_SOURCE_SHA256 "not_built_with_source_digest"
#endif

using json = nlohmann::json;
namespace fs = std::filesystem;
using Steady = std::chrono::steady_clock;
static const std::array<std::string, 3> ROBOTS{"tb1", "tb2", "tb3"};
static const std::vector<std::string> PARAMS{
  "base_frame", "odom_frame", "map_frame", "scan_topic", "transform_timeout",
  "max_laser_range", "minimum_time_interval", "minimum_travel_distance",
  "minimum_travel_heading", "use_scan_matching", "use_scan_barycenter",
  "throttle_scans", "map_update_interval", "resolution", "enable_interactive_mode"};

static void require(bool value, const std::string &reason)
{if (!value) throw std::runtime_error(reason);}

static uint64_t wall_ns()
{return std::chrono::duration_cast<std::chrono::nanoseconds>(Steady::now().time_since_epoch()).count();}

static std::string sha(const uint8_t *data, size_t size)
{
  unsigned char result[SHA256_DIGEST_LENGTH];
  SHA256(data, size, result);
  std::ostringstream out;
  for (unsigned char value : result) out << std::hex << std::setfill('0') << std::setw(2) << unsigned(value);
  return out.str();
}

static std::string read_file(const fs::path &path)
{
  std::ifstream stream(path, std::ios::binary);
  require(bool(stream), "cannot read " + path.string());
  std::ostringstream data; data << stream.rdbuf();
  require(!stream.bad(), "read failure " + path.string());
  return data.str();
}

static std::string sha(const std::string &raw)
{return sha(reinterpret_cast<const uint8_t *>(raw.data()), raw.size());}

static void write_all(int fd, const uint8_t *data, size_t size)
{
  while (size) {
    const auto count = ::write(fd, data, size);
    if (count < 0 && errno == EINTR) continue;
    require(count > 0, "capture write failed");
    data += count; size -= static_cast<size_t>(count);
  }
}

static int exclusive(const fs::path &path)
{
  const int fd = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0644);
  require(fd >= 0, "refusing existing/unavailable output " + path.string());
  return fd;
}

static void exclusive_json(const fs::path &path, const json &value)
{
  const auto data = value.dump(2) + "\n";
  const int fd = exclusive(path);
  try {
    write_all(fd, reinterpret_cast<const uint8_t *>(data.data()), data.size());
    require(::fsync(fd) == 0, "json fsync failed");
  } catch (...) {::close(fd); throw;}
  require(::close(fd) == 0, "json close failed");
}

struct BinarySink
{
  int fd;
  uint64_t offset{0};
  uint64_t maximum;
  explicit BinarySink(const fs::path &path, uint64_t limit) : fd(exclusive(path)), maximum(limit) {}
  ~BinarySink() {if (fd >= 0) ::close(fd);}
  json append(const uint8_t *data, size_t size)
  {
    require(size > 0 && offset <= maximum && size <= maximum - offset, "CDR byte bound reached");
    json result{{"offset", offset}, {"length", size}, {"sha256", sha(data, size)}};
    write_all(fd, data, size); offset += size;
    return result;
  }
  void sync() {require(::fsync(fd) == 0, "CDR fsync failed");}
};

template<typename Stamp> static int64_t stamp_ns(const Stamp &stamp)
{return int64_t(stamp.sec) * 1000000000LL + stamp.nanosec;}

static json scalar(double value)
{
  if (std::isfinite(value)) return value;
  return json{{"finite", false}, {"classification", std::isnan(value) ? "nan" :
    (value > 0 ? "positive_infinity" : "negative_infinity")}};
}

template<typename Message> static json header(const Message &message)
{return json{{"source_ns", stamp_ns(message.header.stamp)}, {"frame_id", message.header.frame_id}};}

static json fields(const sensor_msgs::msg::LaserScan &message)
{
  json counts{{"finite", 0}, {"nan", 0}, {"positive_infinity", 0}, {"negative_infinity", 0}};
  for (float value : message.ranges) {
    const std::string key = std::isfinite(value) ? "finite" : (std::isnan(value) ? "nan" :
      (value > 0 ? "positive_infinity" : "negative_infinity"));
    counts[key] = counts[key].get<size_t>() + 1;
  }
  auto value = header(message);
  value.update(json{{"angle_min", scalar(message.angle_min)}, {"angle_max", scalar(message.angle_max)},
    {"angle_increment", scalar(message.angle_increment)}, {"time_increment", scalar(message.time_increment)},
    {"scan_time", scalar(message.scan_time)}, {"range_min", scalar(message.range_min)},
    {"range_max", scalar(message.range_max)}, {"ranges_count", message.ranges.size()},
    {"intensities_count", message.intensities.size()}, {"ranges_classes", counts}});
  return value;
}

static json fields(const tf2_msgs::msg::TFMessage &message)
{
  json transforms = json::array();
  for (const auto &item : message.transforms) {
    auto value = header(item); value["child_frame_id"] = item.child_frame_id;
    transforms.push_back(value);
  }
  return json{{"transforms", transforms}, {"all_transform_values_in_original_CDR", true}};
}

static json fields(const nav_msgs::msg::Odometry &message)
{auto value = header(message); value["child_frame_id"] = message.child_frame_id; return value;}

static json fields(const geometry_msgs::msg::PoseWithCovarianceStamped &message)
{return header(message);}

static json fields(const nav_msgs::msg::OccupancyGrid &message)
{
  auto value = header(message);
  const auto &p = message.info.origin.position;
  const auto &q = message.info.origin.orientation;
  value.update(json{{"map_load_time_ns", stamp_ns(message.info.map_load_time)},
    {"width", message.info.width}, {"height", message.info.height},
    {"resolution", scalar(message.info.resolution)}, {"data_count", message.data.size()},
    {"origin_position_xyz", {scalar(p.x), scalar(p.y), scalar(p.z)}},
    {"origin_quaternion_xyzw", {scalar(q.x), scalar(q.y), scalar(q.z), scalar(q.w)}}});
  return value;
}

static json fields(const rosgraph_msgs::msg::Clock &message)
{return json{{"clock_ns", stamp_ns(message.clock)}};}

static json qos_json(const rmw_qos_profile_t &qos)
{
  return json{{"history", qos.history}, {"depth", qos.depth}, {"reliability", qos.reliability},
    {"durability", qos.durability}, {"deadline", {qos.deadline.sec, qos.deadline.nsec}},
    {"lifespan", {qos.lifespan.sec, qos.lifespan.nsec}}, {"liveliness", qos.liveliness},
    {"liveliness_lease_duration", {qos.liveliness_lease_duration.sec, qos.liveliness_lease_duration.nsec}},
    {"avoid_ros_namespace_conventions", qos.avoid_ros_namespace_conventions}};
}

static json message_info(const rclcpp::MessageInfo &information)
{
  const auto &info = information.get_rmw_message_info();
  const auto sequence = [](uint64_t value) {
      return json{{"available", value != RMW_MESSAGE_INFO_SEQUENCE_NUMBER_UNSUPPORTED},
        {"value", value == RMW_MESSAGE_INFO_SEQUENCE_NUMBER_UNSUPPORTED ? json(nullptr) : json(value)},
        {"raw_value", value}};
    };
  return json{{"publisher_gid", std::vector<uint8_t>(info.publisher_gid.data,
      info.publisher_gid.data + RMW_GID_STORAGE_SIZE)},
    {"implementation_identifier", info.publisher_gid.implementation_identifier ?
      info.publisher_gid.implementation_identifier : ""},
    {"source_timestamp", info.source_timestamp}, {"received_timestamp", info.received_timestamp},
    {"timestamp_scope", "RMW timestamps; exact take/publish point unspecified; not header simulation stamp"},
    {"publication_sequence", sequence(info.publication_sequence_number)},
    {"reception_sequence", sequence(info.reception_sequence_number)},
    {"from_intra_process", info.from_intra_process}};
}

static json parameter_json(const rcl_interfaces::msg::ParameterValue &value)
{
  return json{{"type", value.type}, {"bool_value", value.bool_value},
    {"integer_value", value.integer_value}, {"double_value", scalar(value.double_value)},
    {"string_value", value.string_value}, {"byte_array_value", value.byte_array_value},
    {"bool_array_value", value.bool_array_value}, {"integer_array_value", value.integer_array_value},
    {"double_array_value", [&value]() {json out = json::array();
      for (double x : value.double_array_value) out.push_back(scalar(x));
      return out;}()},
    {"string_array_value", value.string_array_value}};
}

static std::optional<json> epoch_metadata(const std::string &raw,
  const std::string &expected_freeze, const std::string &run_id)
{
  if (raw.empty() || raw.back() != '\n') return std::nullopt;
  json metadata;
  try {metadata = json::parse(raw);} catch (const json::parse_error &error) {
    if (error.byte == raw.size() + 1) return std::nullopt;
    throw;
  }
  require(metadata.at("schema") == "mr3-p1c-worker-v1" && metadata.at("scene") == "open" &&
    metadata.at("seed").is_number_integer() && metadata.at("seed") == 101 &&
    metadata.at("freeze") == expected_freeze, "worker metadata identity differs");
  const auto epoch = metadata.at("epoch").get<std::string>();
  require(epoch.rfind(run_id + "_w0_e1_", 0) == 0, "worker metadata epoch belongs to another run");
  return metadata;
}

class Recorder : public rclcpp::Node
{
  using List = rcl_interfaces::srv::ListParameters;
  using Get = rcl_interfaces::srv::GetParameters;
  struct ParamState {
    rclcpp::Client<List>::SharedPtr list;
    rclcpp::Client<Get>::SharedPtr get;
    std::string phase{"awaiting_first_map"};
    uint64_t started{0};
  };
  json config_;
  fs::path out_, metadata_, ready_, stop_;
  BinarySink binary_;
  int ledger_;
  uint64_t sequence_{0}, samples_{0}, unbound_samples_{0}, start_{wall_ns()}, clock_{0};
  std::string epoch_, graph_signature_;
  bool stopped_{false}, failed_{false};
  std::string stop_reason_;
  std::vector<rclcpp::SubscriptionBase::SharedPtr> subscriptions_;
  std::map<std::string, std::string> types_;
  std::map<std::string, uint64_t> counts_;
  std::map<std::string, json> requested_qos_;
  std::map<std::string, ParamState> parameters_;
  rclcpp::TimerBase::SharedPtr timer_;

  void record(const std::string &kind, json payload)
  {
    require(sequence_ < config_.at("max_records").get<uint64_t>(), "ledger record bound reached");
    json value{{"schema", "mr3-startup-sensor-ledger-v1"}, {"record_sequence", ++sequence_},
      {"kind", kind}, {"wall_monotonic_ns", wall_ns()}, {"clock_at_receipt_ns", clock_},
      {"epoch", epoch_.empty() ? json(nullptr) : json(epoch_)}, {"payload", payload}};
    const auto raw = value.dump() + "\n";
    write_all(ledger_, reinterpret_cast<const uint8_t *>(raw.data()), raw.size());
  }

  void bind_epoch()
  {
    if (!epoch_.empty() || !fs::exists(metadata_)) return;
    const auto raw = read_file(metadata_);
    const auto parsed = epoch_metadata(raw, config_.at("expected_freeze").get<std::string>(),
      fs::path(config_.at("run_directory").get<std::string>()).filename().string());
    if (!parsed) return;
    epoch_ = parsed->at("epoch").get<std::string>();
    record("epoch_binding", {{"metadata_path", metadata_.string()}, {"metadata_sha256", sha(raw)},
      {"source", "actual worker metadata, written before native launch; messages have no epoch field"}});
  }

  template<typename Message>
  void subscribe(const std::string &topic, const std::string &type, const rclcpp::QoS &qos)
  {
    rclcpp::SubscriptionOptions options;
    options.use_intra_process_comm = rclcpp::IntraProcessSetting::Disable;
    auto callback = [this, topic](const rclcpp::SerializedMessage &raw,
        const rclcpp::MessageInfo &information) {
        if (stopped_) return;
        try {
          bind_epoch();
          const auto &cdr = raw.get_rcl_serialized_message();
          auto blob = binary_.append(cdr.buffer, cdr.buffer_length);
          Message message;
          rclcpp::Serialization<Message> serializer;
          serializer.deserialize_message(&raw, &message);
          if constexpr (std::is_same_v<Message, rosgraph_msgs::msg::Clock>) {
            const auto value = stamp_ns(message.clock);
            require(value >= 0, "negative clock"); clock_ = static_cast<uint64_t>(value);
          }
          record("sample", {{"topic", topic}, {"type", types_.at(topic)},
            {"CDR", blob}, {"message_info", message_info(information)},
            {"decoded_metadata", fields(message)}, {"epoch_binding_available", !epoch_.empty()}});
          ++samples_; ++counts_[topic];
          if (epoch_.empty()) ++unbound_samples_;
          for (const auto &name : ROBOTS) {
            if (topic == "/" + name + "/map" && parameters_.at(name).phase == "awaiting_first_map") {
              parameters_.at(name).phase = "awaiting_services";
              parameters_.at(name).started = wall_ns();
            }
          }
        } catch (const std::exception &error) {fail(error.what());}
      };
    types_[topic] = type;
    counts_[topic] = 0;
    requested_qos_[topic] = qos_json(qos.get_rmw_qos_profile());
    subscriptions_.push_back(create_subscription<Message>(topic, qos, callback, options));
    record("subscription_created", {{"topic", topic}, {"type", type},
      {"requested_qos", qos_json(qos.get_rmw_qos_profile())}});
  }

  void graph()
  {
    json result = json::object();
    for (const auto &item : types_) {
      json entries = json::array();
      for (const auto &endpoint : get_publishers_info_by_topic(item.first)) {
        entries.push_back(json{{"node_name", endpoint.node_name()},
          {"node_namespace", endpoint.node_namespace()}, {"topic_type", endpoint.topic_type()},
          {"endpoint_gid", endpoint.endpoint_gid()},
          {"offered_qos", qos_json(endpoint.qos_profile().get_rmw_qos_profile())}});
      }
      result[item.first] = entries;
    }
    const auto signature = result.dump();
    if (signature != graph_signature_) {
      graph_signature_ = signature;
      record("publisher_graph", {{"topics", result},
        {"scope", "endpoint snapshots in recorder context; per-sample actual GID is separately retained"}});
    }
  }

  void parameter_calls()
  {
    for (auto &item : parameters_) {
      const auto name = item.first;
      auto &state = item.second;
      if (state.started && state.phase != "complete" && state.phase != "unavailable" &&
        wall_ns() - state.started >= uint64_t(config_.at("parameter_wall_guard_sec").get<double>() * 1e9)) {
        record("parameters_unavailable", {{"robot", name}, {"phase", state.phase},
          {"reason", "finite steady-wall guard; no retry or default substitution"}});
        state.phase = "unavailable";
      }
      if (state.phase != "awaiting_services" || !state.list->service_is_ready() ||
        !state.get->service_is_ready()) continue;
      state.phase = "list_requested";
      record("parameter_request", {{"robot", name}, {"service", "/" + name + "/slam_toolbox/list_parameters"},
        {"depth", 0}, {"prefixes", json::array()}});
      auto request = std::make_shared<List::Request>(); request->depth = 0;
      state.list->async_send_request(request, [this, name](rclcpp::Client<List>::SharedFuture future) {
          if (stopped_) return;
          try {
            const auto response = future.get();
            auto &current = parameters_.at(name);
            record("parameter_list_response", {{"robot", name}, {"names", response->result.names},
              {"prefixes", response->result.prefixes}, {"phase_at_response", current.phase}});
            if (current.phase != "list_requested") return;
            current.phase = "get_requested";
            auto request = std::make_shared<Get::Request>(); request->names = PARAMS;
            record("parameter_request", {{"robot", name},
              {"service", "/" + name + "/slam_toolbox/get_parameters"}, {"names", PARAMS}});
            current.get->async_send_request(request, [this, name](rclcpp::Client<Get>::SharedFuture result) {
                if (stopped_) return;
                try {
                  const auto response = result.get();
                  json values = json::array();
                  for (const auto &value : response->values) values.push_back(parameter_json(value));
                  auto &current = parameters_.at(name);
                  record("parameter_values_response", {{"robot", name}, {"requested_names", PARAMS},
                    {"typed_values", values}, {"phase_at_response", current.phase},
                    {"scope", "actual typed read-only service response; NOT_SET is retained, not a default"}});
                  require(values.size() == PARAMS.size(), "parameter response length mismatch");
                  if (current.phase == "get_requested") current.phase = "complete";
                } catch (const std::exception &error) {fail(error.what());}
              });
          } catch (const std::exception &error) {fail(error.what());}
        });
    }
  }

  void fail(const std::string &reason)
  {
    failed_ = true; stop_reason_ = reason; stopped_ = true;
    try {record("recorder_failure", {{"reason", reason}});} catch (...) {}
  }

  void timer()
  {
    if (stopped_) return;
    try {
      bind_epoch(); graph(); parameter_calls();
      if (wall_ns() - start_ >= uint64_t(config_.at("wall_guard_sec").get<double>() * 1e9)) {
        fail("recorder_only_wall_guard_expired; benchmark was not signalled"); return;
      }
      if (fs::exists(stop_)) {
        const auto raw = read_file(stop_);
        if (raw.empty() || raw.back() != '\n') return;
        json marker;
        try {marker = json::parse(raw);} catch (const json::parse_error &error) {
          if (error.byte == raw.size() + 1) return;
          throw;
        }
        require(marker.at("schema") == "mr3-startup-sensor-recorder-stop-v1" &&
          marker.at("run_directory") == config_.at("run_directory") &&
          marker.at("freeze") == config_.at("expected_freeze") &&
          marker.at("reason") == "benchmark_closed", "stop marker identity differs");
        record("normal_stop_marker", {{"path", stop_.string()}, {"sha256", sha(raw)}});
        stop_reason_ = "normal_stop_marker"; stopped_ = true;
      }
    } catch (const std::exception &error) {fail(error.what());}
  }

public:
  Recorder(const json &config, const std::string &configuration_sha)
  : Node("mr3_startup_sensor_recorder", rclcpp::NodeOptions().enable_rosout(false)
      .start_parameter_services(false).start_parameter_event_publisher(false).use_intra_process_comms(false)),
    config_(config), out_(config.at("output_directory").get<std::string>()),
    metadata_(fs::path(config.at("run_directory").get<std::string>()) /
      config.at("episode_relative_directory").get<std::string>() / "metadata.json"),
    ready_(config.at("ready_path").get<std::string>()), stop_(config.at("stop_marker").get<std::string>()),
    binary_(out_ / "messages.cdr", config.at("max_cdr_bytes").get<uint64_t>()),
    ledger_(exclusive(out_ / "records.jsonl"))
  {
    record("configuration", {{"config", config}, {"config_sha256", configuration_sha},
      {"compiled_source_sha256", MR3_RECORDER_SOURCE_SHA256}, {"process_id", ::getpid()},
      {"raw_capture", "actual received serialized CDR; metadata decoding does not replace or rewrite payload"},
      {"no_control", "subscriptions and read-only parameter RPC only; no truth, setter, control publisher or signal"}});
    for (const auto &name : ROBOTS) {
      ParamState state;
      state.list = create_client<List>("/" + name + "/slam_toolbox/list_parameters");
      state.get = create_client<Get>("/" + name + "/slam_toolbox/get_parameters");
      parameters_.emplace(name, std::move(state));
      subscribe<sensor_msgs::msg::LaserScan>("/" + name + "/scan", "sensor_msgs/msg/LaserScan",
        rclcpp::SensorDataQoS().keep_last(64));
      subscribe<tf2_msgs::msg::TFMessage>("/" + name + "/tf", "tf2_msgs/msg/TFMessage",
        rclcpp::QoS(256).best_effort());
      subscribe<tf2_msgs::msg::TFMessage>("/" + name + "/tf_static", "tf2_msgs/msg/TFMessage",
        rclcpp::QoS(64).reliable().transient_local());
      subscribe<nav_msgs::msg::Odometry>("/" + name + "/odom", "nav_msgs/msg/Odometry",
        rclcpp::SensorDataQoS().keep_last(128));
      subscribe<geometry_msgs::msg::PoseWithCovarianceStamped>("/" + name + "/pose",
        "geometry_msgs/msg/PoseWithCovarianceStamped", rclcpp::QoS(64));
      subscribe<nav_msgs::msg::OccupancyGrid>("/" + name + "/map", "nav_msgs/msg/OccupancyGrid",
        rclcpp::QoS(16).reliable().transient_local());
    }
    subscribe<tf2_msgs::msg::TFMessage>("/tf", "tf2_msgs/msg/TFMessage", rclcpp::QoS(256).best_effort());
    subscribe<tf2_msgs::msg::TFMessage>("/tf_static", "tf2_msgs/msg/TFMessage",
      rclcpp::QoS(64).reliable().transient_local());
    subscribe<sensor_msgs::msg::LaserScan>("/scan", "sensor_msgs/msg/LaserScan",
      rclcpp::SensorDataQoS().keep_last(64));
    subscribe<rosgraph_msgs::msg::Clock>("/clock", "rosgraph_msgs/msg/Clock", rclcpp::SensorDataQoS().keep_last(128));
    timer_ = create_wall_timer(std::chrono::milliseconds(100), [this]() {timer();});
    json subscriptions = json::array();
    for (const auto &item : types_) subscriptions.push_back(json{{"topic", item.first},
      {"type", item.second}, {"qos", requested_qos_.at(item.first)}});
    exclusive_json(ready_, {{"schema", "mr3-startup-sensor-recorder-ready-v1"}, {"ready", true},
      {"run_directory", config.at("run_directory")}, {"output_directory", out_.string()},
      {"expected_freeze", config.at("expected_freeze")}, {"config_sha256", configuration_sha},
      {"compiled_source_sha256", MR3_RECORDER_SOURCE_SHA256}, {"process_id", ::getpid()},
      {"subscriptions", subscriptions}, {"epoch_binding", "awaiting_worker_metadata"},
      {"stop_marker", stop_.string()}});
  }
  ~Recorder() override {if (ledger_ >= 0) ::close(ledger_);}
  bool done() const {return stopped_;}
  int finalize()
  {
    json parameters = json::object();
    for (const auto &item : parameters_) parameters[item.first] = item.second.phase;
    record("recorder_end", {{"reason", stop_reason_}, {"failed", failed_},
      {"sample_count", samples_}, {"topic_counts", counts_}, {"parameter_states", parameters},
      {"cdr_bytes", binary_.offset}, {"wall_duration_sec", (wall_ns() - start_) / 1e9}});
    binary_.sync(); require(::fsync(ledger_) == 0, "ledger fsync failed");
    exclusive_json(out_ / "final.json", {{"schema", "mr3-startup-sensor-recorder-final-v1"},
      {"capture_completed", !failed_ && stop_reason_ == "normal_stop_marker"},
      {"normal_stop", !failed_ && stop_reason_ == "normal_stop_marker"}, {"failed", failed_},
      {"reason", stop_reason_}, {"epoch", epoch_}, {"records", sequence_}, {"samples", samples_},
      {"topic_counts", counts_}, {"parameter_states", parameters}, {"cdr_bytes", binary_.offset},
      {"unbound_epoch_samples", unbound_samples_},
      {"source_sha256", MR3_RECORDER_SOURCE_SHA256}, {"source_scope", "pure diagnostic capture, not task or matrix PASS"}});
    return failed_ ? 1 : 0;
  }
};

static json validate_config(const std::string &raw)
{
  auto config = json::parse(raw);
  const std::vector<std::string> keys{"schema", "run_directory", "episode_relative_directory",
    "output_directory", "ready_path", "stop_marker", "expected_freeze", "expected_domain_id",
    "wall_guard_sec", "max_cdr_bytes", "max_records", "parameter_wall_guard_sec"};
  require(config.is_object() && config.size() == keys.size(), "unknown configuration fields");
  for (const auto &key : keys) require(config.contains(key), "missing configuration field");
  require(config.at("schema") == "mr3-startup-sensor-capture-config-v1", "unknown config schema");
  require(config.at("episode_relative_directory") == "worker0/episode001_open_101", "wrong episode path");
  for (const auto &key : {"run_directory", "output_directory", "ready_path", "stop_marker"}) {
    require(config.at(key).is_string(), "path must be string");
    require(fs::path(config.at(key).get<std::string>()).is_absolute(), "path must be absolute");
  }
  const auto freeze = config.at("expected_freeze").get<std::string>();
  require(freeze.size() == 40 && freeze.find_first_not_of("0123456789abcdef") == std::string::npos, "invalid freeze");
  for (const auto &key : {"max_cdr_bytes", "max_records", "expected_domain_id"})
    require(config.at(key).is_number_unsigned() || config.at(key).is_number_integer(), "integer bound required");
  require(config.at("max_cdr_bytes").get<int64_t>() > 0 && config.at("max_cdr_bytes").get<int64_t>() <= 268435456,
    "CDR limit outside declared diagnostic bound");
  require(config.at("max_records").get<int64_t>() > 0 && config.at("max_records").get<int64_t>() <= 1000000,
    "record limit outside declared diagnostic bound");
  require(config.at("expected_domain_id").get<int64_t>() >= 0 &&
    config.at("expected_domain_id").get<int64_t>() <= 232, "ROS domain outside valid local range");
  for (const auto &key : {"wall_guard_sec", "parameter_wall_guard_sec"}) {
    require(config.at(key).is_number() && std::isfinite(config.at(key).get<double>()), "finite guard required");
    require(config.at(key).get<double>() > 0 && config.at(key).get<double>() <= 1000, "guard outside diagnostic bound");
  }
  return config;
}

static void self_test()
{
  char pattern[] = "/tmp/mr3_sensor_cpu_XXXXXX";
  const auto directory = ::mkdtemp(pattern); require(directory, "mkdtemp failed");
  const fs::path path = fs::path(directory) / "test.cdr";
  try {
    require(sha("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", "SHA known answer");
    sensor_msgs::msg::LaserScan message;
    message.header.frame_id = "tb1/base_scan"; message.range_min = .12f; message.range_max = 10.f;
    const std::vector<uint32_t> bits{0x7f800000, 0xff800000, 0x7fc00001, 0x7fc12345, 0x3df5c28f, 0};
    for (auto value : bits) {float x; std::memcpy(&x, &value, 4); message.ranges.push_back(x);}
    message.intensities = {1.f, 2.f, 3.f};
    rclcpp::Serialization<sensor_msgs::msg::LaserScan> serialization;
    rclcpp::SerializedMessage serialized;
    serialization.serialize_message(&message, &serialized);
    const auto &cdr = serialized.get_rcl_serialized_message();
    BinarySink sink(path, cdr.buffer_length * 2);
    const auto first = sink.append(cdr.buffer, cdr.buffer_length);
    const auto second = sink.append(cdr.buffer, cdr.buffer_length);
    require(first.at("offset") == 0 && second.at("offset") == cdr.buffer_length, "offset order");
    require(first.at("sha256") == second.at("sha256"), "payload SHA");
    bool rejected = false; try {sink.append(cdr.buffer, 1);} catch (...) {rejected = true;}
    require(rejected && sink.offset == cdr.buffer_length * 2, "bound must refuse without append");
    sink.sync(); const auto bytes = read_file(path);
    require(bytes.size() == cdr.buffer_length * 2 &&
      std::memcmp(bytes.data(), cdr.buffer, cdr.buffer_length) == 0 &&
      std::memcmp(bytes.data() + cdr.buffer_length, cdr.buffer, cdr.buffer_length) == 0, "exact CDR roundtrip");
    sensor_msgs::msg::LaserScan restored; serialization.deserialize_message(&serialized, &restored);
    require(restored.intensities == message.intensities, "intensity roundtrip");
    for (size_t i = 0; i < bits.size(); ++i) {uint32_t value;
      std::memcpy(&value, &restored.ranges[i], 4); require(value == bits[i], "nonfinite float32 bit pattern changed");}
    const auto meta = fields(restored);
    require(meta.at("ranges_classes").at("nan") == 2 &&
      meta.at("ranges_classes").at("positive_infinity") == 1 &&
      meta.at("ranges_classes").at("negative_infinity") == 1, "nonfinite metadata classes");
    rclcpp::MessageInfo info;
    auto &rmw = info.get_rmw_message_info();
    rmw.publication_sequence_number = RMW_MESSAGE_INFO_SEQUENCE_NUMBER_UNSUPPORTED;
    rmw.reception_sequence_number = 3;
    rmw.publisher_gid.data[0] = 42;
    const auto captured = message_info(info);
    require(captured.at("publication_sequence").at("available") == false &&
      captured.at("publication_sequence").at("value").is_null() &&
      captured.at("reception_sequence").at("raw_value") == 3 &&
      captured.at("publisher_gid").at(0) == 42, "messageinfo field preservation");
    require(scalar(std::numeric_limits<double>::infinity()).at("finite") == false, "nonfinite JSON tag");
    json worker{{"schema", "mr3-p1c-worker-v1"}, {"scene", "open"}, {"seed", 101},
      {"freeze", std::string(40, 'a')}, {"epoch", "fixture_w0_e1_cpu"}};
    require(!epoch_metadata("{\n", std::string(40, 'a'), "fixture"), "partial worker must remain pending");
    require(!epoch_metadata(worker.dump(), std::string(40, 'a'), "fixture"), "worker newline not yet written");
    require(bool(epoch_metadata(worker.dump() + "\n", std::string(40, 'a'), "fixture")), "complete epoch binding");
    rejected = false;
    try {epoch_metadata(worker.dump() + "\n", std::string(40, 'b'), "fixture");} catch (...) {rejected = true;}
    require(rejected, "complete wrong worker identity must fail");
    rejected = false;
    try {epoch_metadata(worker.dump() + "\n", std::string(40, 'a'), "other_run");} catch (...) {rejected = true;}
    require(rejected, "wrong run epoch must fail");
    json config{{"schema", "mr3-startup-sensor-capture-config-v1"}, {"run_directory", "/tmp/fixture"},
      {"episode_relative_directory", "worker0/episode001_open_101"}, {"output_directory", "/tmp/fixture_out"},
      {"ready_path", "/tmp/fixture_ready"}, {"stop_marker", "/tmp/fixture_stop"},
      {"expected_freeze", std::string(40, 'a')}, {"expected_domain_id", 171},
      {"wall_guard_sec", 1000}, {"max_cdr_bytes", 268435456}, {"max_records", 1000000},
      {"parameter_wall_guard_sec", 20}};
    validate_config(config.dump());
    auto bad_config = config; bad_config["max_records"] = true;
    rejected = false; try {validate_config(bad_config.dump());} catch (...) {rejected = true;}
    require(rejected, "bool cannot replace numeric bound");
    bad_config = config; bad_config["unknown"] = 1;
    rejected = false; try {validate_config(bad_config.dump());} catch (...) {rejected = true;}
    require(rejected, "unknown configuration must fail");
    nav_msgs::msg::OccupancyGrid grid;
    grid.header.frame_id = "tb1/map"; grid.header.stamp.sec = 2;
    grid.info.width = 2; grid.info.height = 2; grid.info.resolution = .05f;
    grid.info.origin.orientation.w = 1.; grid.data = {-1, 0, 100, 42};
    rclcpp::Serialization<nav_msgs::msg::OccupancyGrid> grid_serialization;
    rclcpp::SerializedMessage grid_raw; grid_serialization.serialize_message(&grid, &grid_raw);
    nav_msgs::msg::OccupancyGrid grid_copy;
    grid_serialization.deserialize_message(&grid_raw, &grid_copy);
    require(grid_copy.data == grid.data && fields(grid_copy).at("data_count") == 4,
      "occupancy unknown/free/100 bytes preserved");
    tf2_msgs::msg::TFMessage tf;
    geometry_msgs::msg::TransformStamped transform;
    transform.header.frame_id = "map"; transform.child_frame_id = "tb1/odom";
    transform.header.stamp.sec = 3; transform.transform.rotation.w = 1.;
    tf.transforms.push_back(transform); transform.child_frame_id = "unprefixed_scan";
    transform.header.stamp.sec = 0; tf.transforms.push_back(transform);
    require(fields(tf).at("transforms").size() == 2 &&
      fields(tf).at("transforms").at(1).at("child_frame_id") == "unprefixed_scan",
      "all TF transforms and actual unprefixed frames retained");
    std::cout << json{{"CPU_self_test_completed", true}, {"ROS_DDS_initialized", false},
      {"checks", {"SHA_known_answer", "raw_CDR_offsets", "raw_CDR_byte_roundtrip", "bound_no_append",
        "LaserScan_inf_NaN_payload_bits", "LaserScan_intensities", "nonfinite_class_tags",
        "MessageInfo_unavailable_seq_and_GID", "partial_epoch_pending", "full_wrong_epoch_rejected",
        "wrong_run_rejected", "typed_configuration_bounds", "unknown_config_rejected",
        "occupancy_int8_roundtrip", "all_TF_frames_retained"}}}.dump() << std::endl;
  } catch (...) {fs::remove_all(directory); throw;}
  fs::remove_all(directory);
}

int main(int argc, char **argv)
{
  try {
    if (argc == 2 && std::string(argv[1]) == "--self-test") {self_test(); return 0;}
    require(argc == 3 && std::string(argv[1]) == "--config", "usage: recorder --config ABS_JSON | --self-test");
    const auto raw = read_file(argv[2]); const auto config = validate_config(raw);
    require(std::string(MR3_RECORDER_SOURCE_SHA256).size() == 64, "compiled source macro missing");
    const auto domain = std::getenv("ROS_DOMAIN_ID");
    require(domain && std::string(domain) == std::to_string(config.at("expected_domain_id").get<int>()), "ROS domain differs");
    const fs::path output = config.at("output_directory").get<std::string>();
    require(!fs::exists(output), "output directory already exists");
    require(!fs::exists(config.at("ready_path").get<std::string>()) &&
      !fs::exists(config.at("stop_marker").get<std::string>()), "ready/stop marker already exists");
    require(fs::create_directory(output), "cannot create capture output");
    rclcpp::init(0, nullptr);
    auto node = std::make_shared<Recorder>(config, sha(raw));
    rclcpp::executors::SingleThreadedExecutor executor; executor.add_node(node);
    while (rclcpp::ok() && !node->done()) executor.spin_once(std::chrono::milliseconds(20));
    require(node->done(), "ROS context shutdown before normal recorder completion");
    const int result = node->finalize(); executor.remove_node(node); node.reset(); rclcpp::shutdown(); return result;
  } catch (const std::exception &error) {
    std::cerr << "RECORDER_ERROR " << error.what() << std::endl;
    if (rclcpp::ok()) rclcpp::shutdown();
    return 2;
  }
}
