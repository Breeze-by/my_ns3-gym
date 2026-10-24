/*
 * Ray/box collision correction derived from Gazebo Classic 11.10.2's bundled
 * Open Dynamics Engine ray.cpp. Copyright (C) 2001-2003 Russell L. Smith.
 * This derivative selects the BSD-style license in LICENSE-BSD.TXT.
 */
#ifndef MULTI_ROBOT_MR3_RAY_BOX_COLLISION_HPP_
#define MULTI_ROBOT_MR3_RAY_BOX_COLLISION_HPP_

#include <gazebo/ode/ode.h>
#include <array>

namespace multi_robot
{
namespace ray_box
{
struct Input
{
  std::array<dReal, 3> start;
  std::array<dReal, 3> direction;
  std::array<dReal, 3> lengths;
  std::array<dReal, 3> world_start;
  std::array<dReal, 3> world_direction;
  std::array<dReal, 12> box_rotation;
  dReal max_length;
};

struct Result
{
  bool hit = false;
  long double depth = 0;
  int axis = 0;
  dReal normal_sign = 0;
};

// Read public ODE primitives. Caller uses the normal ODE collision critical
// section. These getters may refresh derived geom-pose caches, not cast rays.
Input ReadInput(dGeomID ray, dGeomID box);

// Complete finite segment / oriented box test. Every nonzero direction axis
// contributes a slab. No legacy shadow calculation runs in production.
Result Solve(const Input &input);

int WriteContact(dGeomID ray, dGeomID box, const Input &input,
  const Result &result, dContactGeom *contact);

// Public dColliderFn-compatible callback; no recursive dCollide call.
int CorrectRayBox(dGeomID ray, dGeomID box, int flags,
  dContactGeom *contact, int skip);
}  // namespace ray_box
}  // namespace multi_robot
#endif
