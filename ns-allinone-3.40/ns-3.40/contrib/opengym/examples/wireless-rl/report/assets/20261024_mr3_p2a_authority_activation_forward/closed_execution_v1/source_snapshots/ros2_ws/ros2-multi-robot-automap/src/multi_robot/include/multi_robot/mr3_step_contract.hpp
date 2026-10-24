#pragma once

#include <cstdint>
#include <stdexcept>
#include <string>
#include <nlohmann/json.hpp>

namespace mr3 {
using Json = nlohmann::json;

struct StepRequest {
  std::string epoch;
  std::string request_id;
  unsigned int steps;
  std::int64_t step_ns;
};

inline StepRequest ParseStepRequest(const Json & input) {
  if (!input.is_object() || !input.contains("epoch") || !input["epoch"].is_string() ||
      input["epoch"].get<std::string>().empty() || !input.contains("request_id") ||
      !input["request_id"].is_string() || input["request_id"].get<std::string>().empty() ||
      !input.contains("steps") || !input["steps"].is_number_integer()) {
    throw std::invalid_argument("epoch, request_id and integer steps are required");
  }
  const auto steps = input["steps"].get<std::int64_t>();
  const auto step_ns = input.value("step_ns", std::int64_t{1000000});
  if (steps < 0 || steps > 1000 || step_ns != 1000000) {
    throw std::invalid_argument("steps must be 0..1000 at the frozen 1 ms physics tick");
  }
  return {input["epoch"], input["request_id"], static_cast<unsigned int>(steps), step_ns};
}

inline void CheckEpoch(const std::string & requested, const std::string & active) {
  if (!active.empty() && requested != active) {
    throw std::invalid_argument("cross-epoch physics request; rebuild the worker");
  }
}

inline bool ExactStep(std::int64_t start_ns, std::int64_t end_ns,
                     std::uint64_t start_iterations, std::uint64_t end_iterations,
                     unsigned int steps, std::int64_t step_ns, bool paused) {
  return paused && end_ns >= start_ns && end_iterations >= start_iterations &&
    end_iterations - start_iterations == steps &&
    end_ns - start_ns == static_cast<std::int64_t>(steps) * step_ns;
}
}  // namespace mr3
