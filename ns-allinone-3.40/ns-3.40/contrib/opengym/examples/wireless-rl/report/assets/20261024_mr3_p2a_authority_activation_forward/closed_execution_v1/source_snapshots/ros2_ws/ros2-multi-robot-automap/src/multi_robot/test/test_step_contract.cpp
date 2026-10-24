#include <gtest/gtest.h>
#include "multi_robot/mr3_step_contract.hpp"

TEST(StepContract, AcceptsOnlyBoundedRealPhysicsTicks) {
  const mr3::Json valid{{"epoch", "a"}, {"request_id", "1"}, {"steps", 20}};
  EXPECT_EQ(mr3::ParseStepRequest(valid).steps, 20u);
  for (const auto steps : {-1, 1001}) {
    auto bad = valid;
    bad["steps"] = steps;
    EXPECT_THROW(mr3::ParseStepRequest(bad), std::invalid_argument);
  }
  auto bad = valid;
  bad["steps"] = 20.5;
  EXPECT_THROW(mr3::ParseStepRequest(bad), std::invalid_argument);
  bad = valid;
  bad["step_ns"] = 2000000;
  EXPECT_THROW(mr3::ParseStepRequest(bad), std::invalid_argument);
}

TEST(StepContract, RequiresEpochAndRequestIdentity) {
  EXPECT_THROW(mr3::ParseStepRequest(mr3::Json{{"steps", 20}}), std::invalid_argument);
  EXPECT_NO_THROW(mr3::CheckEpoch("episode-a", ""));
  EXPECT_NO_THROW(mr3::CheckEpoch("episode-a", "episode-a"));
  EXPECT_THROW(mr3::CheckEpoch("episode-b", "episode-a"), std::invalid_argument);
}

TEST(StepContract, RequiresBothIterationAndTimeAdvanceWithPause) {
  EXPECT_TRUE(mr3::ExactStep(1000000000, 1020000000, 1000, 1020, 20, 1000000, true));
  EXPECT_TRUE(mr3::ExactStep(1000000000, 1000000000, 1000, 1000, 0, 1000000, true));
  EXPECT_FALSE(mr3::ExactStep(1000000000, 1020000001, 1000, 1020, 20, 1000000, true));
  EXPECT_FALSE(mr3::ExactStep(1000000000, 1020000000, 1000, 1019, 20, 1000000, true));
  EXPECT_FALSE(mr3::ExactStep(1000000000, 1020000000, 1000, 1020, 20, 1000000, false));
  EXPECT_FALSE(mr3::ExactStep(1000000000, 999000000, 1000, 999, 20, 1000000, true));
}
