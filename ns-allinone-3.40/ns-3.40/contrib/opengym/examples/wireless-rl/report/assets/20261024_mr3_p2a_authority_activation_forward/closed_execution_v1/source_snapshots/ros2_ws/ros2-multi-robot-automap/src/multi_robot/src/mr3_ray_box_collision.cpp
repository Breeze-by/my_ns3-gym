/*
 * Ray/box collision correction derived from Gazebo Classic 11.10.2's bundled
 * Open Dynamics Engine ray.cpp. Copyright (C) 2001-2003 Russell L. Smith.
 * This derivative selects the BSD-style license in LICENSE-BSD.TXT.
 *
 * Changes: obtain primitives through public ODE APIs; constrain every nonzero
 * direction axis; use long-double interval arithmetic to avoid binary64
 * quotient overflow for finite near-parallel inputs. Preserve original
 * ray-first contact identity and opposite-travel normal / inside-exit rules.
 */
#include "multi_robot/mr3_ray_box_collision.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace multi_robot
{
namespace ray_box
{
Input ReadInput(dGeomID ray, dGeomID box)
{
  if (!ray || !box || dGeomGetClass(ray) != dRayClass ||
      dGeomGetClass(box) != dBoxClass)
    throw std::runtime_error("ray-box callback received incompatible geoms");
  dVector3 start, direction, lengths;
  dGeomRayGet(ray, start, direction);
  dGeomBoxGetLengths(box, lengths);
  const dReal *position = dGeomGetPosition(box);
  const dReal *rotation = dGeomGetRotation(box);
  dVector3 relative, localStart, localDirection;
  for (int i = 0; i < 3; ++i)
    relative[i] = start[i] - position[i];
  // Same binary64 transforms as the original ODE ray-box callback.
  dMultiply1_331(localStart, rotation, relative);
  dMultiply1_331(localDirection, rotation, direction);
  Input result{};
  for (int i = 0; i < 3; ++i)
  {
    result.start[i] = localStart[i];
    result.direction[i] = localDirection[i];
    result.lengths[i] = lengths[i];
    result.world_start[i] = start[i];
    result.world_direction[i] = direction[i];
  }
  for (int row = 0; row < 3; ++row)
    for (int column = 0; column < 3; ++column)
      result.box_rotation[row * 4 + column] = rotation[row * 4 + column];
  result.max_length = dGeomRayGetLength(ray);
  return result;
}

Result Solve(const Input &input)
{
  if (!std::isfinite(input.max_length) || input.max_length < 0)
    throw std::runtime_error("nonfinite/negative native ray length");
  std::array<long double, 3> s{}, v{}, half{};
  std::array<dReal, 3> sign{};
  bool anyDirection = false;
  for (int i = 0; i < 3; ++i)
  {
    if (!std::isfinite(input.start[i]) ||
        !std::isfinite(input.direction[i]) ||
        !std::isfinite(input.lengths[i]) || input.lengths[i] < 0)
      throw std::runtime_error("invalid native ray-box primitive");
  }
  for (int i = 0; i < 3; ++i)
  {
    s[i] = input.start[i];
    v[i] = input.direction[i];
    half[i] = static_cast<long double>(input.lengths[i]) / 2;
    anyDirection = anyDirection || v[i] != 0;
    sign[i] = v[i] < 0 ? 1 : -1;
    if (v[i] < 0)
    {
      s[i] = -s[i];
      v[i] = -v[i];
    }
    // Retain the original mirrored exact early-exit rules.
    if ((s[i] < -half[i] && v[i] <= 0) || s[i] > half[i])
      return {};
  }
  if (!anyDirection)
    throw std::runtime_error("native ray direction has no nonzero component");
  long double lo = -std::numeric_limits<long double>::infinity();
  long double hi = std::numeric_limits<long double>::infinity();
  int nearAxis = 0;
  int farAxis = 0;
  for (int i = 0; i < 3; ++i)
  {
    if (v[i] == 0)
      continue;
    long double t = (-half[i] - s[i]) / v[i];
    if (t > lo)
    {
      lo = t;
      nearAxis = i;
    }
    t = (half[i] - s[i]) / v[i];
    if (t < hi)
    {
      hi = t;
      farAxis = i;
    }
  }
  if (lo > hi)
    return {};
  const bool entering = lo >= 0;
  const long double depth = entering ? lo : hi;
  if (depth < 0 || depth > input.max_length || !std::isfinite(depth))
    return {};
  const int axis = entering ? nearAxis : farAxis;
  return {true, depth, axis, sign[axis]};
}

int WriteContact(dGeomID ray, dGeomID box, const Input &input,
  const Result &result, dContactGeom *contact)
{
  if (!result.hit)
    return 0;
  const dReal depth = static_cast<dReal>(result.depth);
  contact->g1 = ray;
  contact->g2 = box;
  contact->side1 = -1;
  contact->side2 = -1;
  for (int i = 0; i < 3; ++i)
  {
    contact->pos[i] = input.world_start[i] + depth * input.world_direction[i];
    contact->normal[i] = input.box_rotation[i * 4 + result.axis] *
      result.normal_sign;
  }
  contact->depth = depth;
  return 1;
}

int CorrectRayBox(dGeomID ray, dGeomID box, int flags,
  dContactGeom *contact, int skip)
{
  if (!contact || skip < static_cast<int>(sizeof(dContactGeom)) ||
      (flags & 0xffff) == 0)
    return 0;
  const auto input = ReadInput(ray, box);
  return WriteContact(ray, box, input, Solve(input), contact);
}
}  // namespace ray_box
}  // namespace multi_robot
