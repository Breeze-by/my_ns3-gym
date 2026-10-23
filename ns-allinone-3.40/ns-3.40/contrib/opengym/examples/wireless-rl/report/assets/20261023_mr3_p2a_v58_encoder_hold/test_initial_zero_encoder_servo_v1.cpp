#include "initial_zero_encoder_servo_v1.hpp"
#include <iostream>
#include <limits>
#include <stdexcept>
#include <vector>
using namespace multi_robot::mr3_v58;
static unsigned checks = 0;
static void need(bool ok, const char * why) { if (!ok) throw std::runtime_error(why); }
static bool same(const ServoState & a, const ServoState & b) {
  return a.armed == b.armed && a.reference_valid == b.reference_valid &&
    a.capture_count == b.capture_count && a.rest_samples == b.rest_samples && a.reference == b.reference;
}
static void capture(InitialZeroEncoderServo & s, std::array<double, 2> q={1.0, -2.0}) {
  s.update(q, {0.0, 0.0}, 0.0, 0.0);
  s.update(q, {0.0, 0.0}, 0.0, 0.0);
  auto r=s.update(q, {0.0, 0.0}, 0.0, 0.0);
  need(r.captured_this_update && r.capture_count == 1 && r.reference == q, "three-update capture");
}
int main() {
  try {
    { InitialZeroEncoderServo s;
      auto a=s.update({1, 2}, {0, 0}, 0, 0); auto b=s.update({3, 4}, {0, 0}, 0, 0);
      auto c=s.update({5, 6}, {0, 0}, 0, 0);
      need(!a.reference_valid && !b.reference_valid && c.reference_valid && c.reference==std::array<double,2>{5,6}, "capture at actual third sample");
      need(a.rest_samples==1 && b.rest_samples==2 && c.rest_samples==3 && c.captured_this_update, "sample counter"); ++checks; }
    { InitialZeroEncoderServo s; capture(s);
      auto r=s.update({1.02, -2.03}, {0, 0}, 0, 0);
      need(r.reference==std::array<double,2>{1,-2} && r.capture_count==1 && !r.captured_this_update, "no reference refresh");
      need(r.servo_desired_rim[0]==WHEEL_RADIUS*(1.0-1.02)*POSITION_GAIN && r.servo_desired_rim[1]==WHEEL_RADIUS*(-2.0+2.03)*POSITION_GAIN, "signed P correction");
      need(r.limited.applied==r.servo_desired_rim && r.feedback_active, "real nonzero correction disclosed"); ++checks; }
    { InitialZeroEncoderServo s; s.update({0,0},{0,0},0,0);
      auto r=s.update({0,0},{1,0},0,0); need(r.rest_samples==0 && !r.reference_valid,"non-rest resets consecutive samples");
      s.update({1,1},{0,0},0,0); r=s.update({1,1},{0,0},0,0); need(!r.reference_valid,"only two after reset");
      r=s.update({2,2},{0,0},0,0); need(r.reference==std::array<double,2>{2,2} && r.capture_count==1,"capture after three consecutive"); ++checks; }
    { InitialZeroEncoderServo s; auto r=s.update({0,0},{0,0},0,.1); need(!r.armed && !r.reference_valid,"pure turn disarms");
      for(int i=0;i<50;++i) r=s.update({double(i),double(i)},{0,0},0,0);
      need(!r.armed && !r.reference_valid && r.capture_count==0 && !r.feedback_active,"never rearm after pure turn"); ++checks; }
    { InitialZeroEncoderServo s; capture(s); auto r=s.update({1,-2},{2,-3},.1,0);
      const auto ref=r.reference; need(!r.armed && r.reference_valid && !r.feedback_active,"post-capture nonzero disarms without erasing proof");
      r=s.update({20,-20},{2,-3},0,0); auto old=multi_robot::limit_paired_wheel_speeds(r.current_rim,{0,0},1,.034);
      need(r.reference==ref && r.capture_count==1 && r.limited.applied==old.applied && r.limited.alpha==old.alpha,"zero after disarm uses original law"); ++checks; }
    { for(auto target:std::vector<std::array<double,2>>{{.2,0},{0,.8},{-.1,-.6},{.17,.05}}) {
        InitialZeroEncoderServo s; auto r=s.update({2,-3},{2,-3},target[0],target[1]);
        const std::array<double,2> desired{target[0]+target[1]*.287/2,target[0]-target[1]*.287/2};
        const auto old=multi_robot::limit_paired_wheel_speeds({2*.033,-3*.033},desired,1,.034);
        need(r.limited.applied==old.applied && r.limited.alpha==old.alpha && r.servo_desired_rim==desired,"nonzero original law exact equivalence");
      } ++checks; }
    { InitialZeroEncoderServo s; capture(s,{0,0}); auto r=s.update({100,-100},{0,0},0,0);
      need(r.servo_desired_rim==std::array<double,2>{-.005,.005} && r.limited.applied==r.servo_desired_rim,"finite signed saturation"); ++checks; }
    { InitialZeroEncoderServo s; s.update({0,0},{0,0},0,0); const auto before=s.state();
      const double nan=std::numeric_limits<double>::quiet_NaN(), inf=std::numeric_limits<double>::infinity();
      for(int variant=0;variant<7;++variant) {
        bool threw=false; try { switch(variant) {
          case 0:s.update({nan,0},{0,0},1,0);break;
          case 1:s.update({0,0},{inf,0},0,0);break;
          case 2:s.update({0,0},{0,0},nan,0);break;
          case 3:s.update({0,0},{0,0},0,inf);break;
          case 4:s.update({0,0},{0,0},0,0,0);break;
          case 5:s.update({0,0},{0,0},0,0,-1);break;
          default:s.update({0,0},{0,0},0,0,68000000); }
        } catch(const std::invalid_argument &) {threw=true;}
        need(threw && same(before,s.state()),"invalid update leaves state unchanged");
      }
      s.update({0,0},{0,0},0,0); auto r=s.update({3,4},{0,0},0,0);
      need(r.capture_count==1 && r.reference==std::array<double,2>{3,4},"invalid nonzero did not disarm"); ++checks; }
    { InitialZeroEncoderServo s; capture(s,{-1e308,0}); const auto before=s.state(); bool threw=false;
      try{s.update({1e308,0},{0,0},0,0);}catch(const std::invalid_argument &){threw=true;}
      need(threw && same(before,s.state()),"overflow feedback is atomic rejection"); ++checks; }
    { InitialZeroEncoderServo s; auto r=s.update({0,0},{0,0},std::numeric_limits<double>::denorm_min(),0);
      need(!r.armed,"subnormal nonzero body target disarms"); ++checks; }
    { InitialZeroEncoderServo s; capture(s,{0,0}); auto r=s.update({100,-100},{10,-8},0,0);
      const auto old=multi_robot::limit_paired_wheel_speeds(r.current_rim,r.servo_desired_rim,1,.034);
      need(r.limited.applied==old.applied && r.limited.alpha==old.alpha,"feedback keeps original common fraction");
      for(unsigned i=0;i<2;++i) { need(std::abs((long double)r.limited.applied[i]-r.current_rim[i]) <= (long double).034,"per-wheel real acceleration budget"); } ++checks; }
    { InitialZeroEncoderServo s; capture(s,{3.13,3.13}); auto r=s.update({-3.13,-3.13},{0,0},0,0);
      need(r.reference==std::array<double,2>{3.13,3.13} && r.servo_desired_rim==std::array<double,2>{.005,.005},"no hidden angle unwrap or reference reset"); ++checks; }
    std::cout << "{\"passed\":true,\"checks\":" << checks << ",\"World_runs\":0,\"physical_credit\":false}\n";
    return 0;
  } catch(const std::exception & error) { std::cerr << error.what() << '\n'; return 1; }
}
