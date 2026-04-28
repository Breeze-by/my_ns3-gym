/* -*-  Mode: C++; c-file-style: "gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2018 Piotr Gawlowicz
 *
 * Modified for a simple wireless resource allocation ns3-gym example.
 */

#include "ns3/core-module.h"
#include "ns3/opengym-module.h"

#include <algorithm>
#include <cmath>
#include <sstream>
#include <vector>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE ("WirelessRl");

static const uint32_t userNum = 5;
static const uint32_t maxQueue = 100;
static const uint32_t maxCqi = 10;
static const uint32_t maxDelay = 20;
static const uint32_t deadline = 8;
static uint32_t g_maxSteps = 40;

static std::vector<uint32_t> g_cqi(userNum, 1);
static std::vector<uint32_t> g_queue(userNum, 0);
// Per-user backlog age. This is not per-packet delay.
static std::vector<uint32_t> g_delay(userNum, 0);

static uint32_t g_lastServedUser = 0;
static float g_lastThroughput = 0.0;
static float g_lastReward = 0.0;
static float g_lastRewardQueue = 0.0;
static float g_lastTotalDelay = 0.0;
static uint32_t g_lastDeadlineMisses = 0;

static uint32_t g_step = 0;
static Ptr<UniformRandomVariable> g_rng;
static bool g_verbose = false;


/*
 * Calculate total queue length.
 */
float
GetTotalQueue()
{
  float totalQueue = 0.0;

  for (uint32_t i = 0; i < userNum; i++)
    {
      totalQueue += g_queue[i];
    }

  return totalQueue;
}


float
GetTotalDelay()
{
  float totalDelay = 0.0;

  for (uint32_t i = 0; i < userNum; i++)
    {
      totalDelay += g_delay[i];
    }

  return totalDelay;
}


uint32_t
GetDeadlineMisses()
{
  /*
   * Count users that are currently backlogged and already beyond the
   * deadline. This is a persistent per-step pressure signal, not a
   * cumulative packet drop count and not only newly missed deadlines.
   */
  uint32_t misses = 0;

  for (uint32_t i = 0; i < userNum; i++)
    {
      if (g_queue[i] > 0 && g_delay[i] > deadline)
        {
          misses++;
        }
    }

  return misses;
}


/*
 * Define observation space:
 *   [cqi0, queue0, delay0, ..., cqi4, queue4, delay4]
 */
Ptr<OpenGymSpace>
MyGetObservationSpace(void)
{
  float low = 0.0;
  float high = 100.0;

  std::vector<uint32_t> shape = {userNum * 3,};
  std::string dtype = TypeNameGet<uint32_t> ();

  Ptr<OpenGymBoxSpace> space =
      CreateObject<OpenGymBoxSpace> (low, high, shape, dtype);

  if (g_verbose)
    {
      NS_LOG_UNCOND ("MyGetObservationSpace: " << space);
    }

  return space;
}


/*
 * Define action space:
 *   action i means serving user i in this time slot.
 */
Ptr<OpenGymSpace>
MyGetActionSpace(void)
{
  Ptr<OpenGymDiscreteSpace> space =
      CreateObject<OpenGymDiscreteSpace> (userNum);

  if (g_verbose)
    {
      NS_LOG_UNCOND ("MyGetActionSpace: " << space);
    }

  return space;
}


/*
 * Define game over condition.
 *
 * Here, one episode ends after g_maxSteps scheduling decisions.
 */
bool
MyGetGameOver(void)
{
  bool isGameOver = (g_step >= g_maxSteps);

  if (g_verbose)
    {
      NS_LOG_UNCOND ("MyGetGameOver: " << isGameOver);
    }

  return isGameOver;
}


/*
 * Collect observations.
 *
 * The Python agent will receive:
 *   [cqi0, queue0, delay0, ..., cqi4, queue4, delay4]
 */
Ptr<OpenGymDataContainer>
MyGetObservation(void)
{
  std::vector<uint32_t> shape = {userNum * 3,};

  Ptr<OpenGymBoxContainer<uint32_t> > box =
      CreateObject<OpenGymBoxContainer<uint32_t> > (shape);

  for (uint32_t i = 0; i < userNum; i++)
    {
      box->AddValue(g_cqi[i]);
      box->AddValue(g_queue[i]);
      box->AddValue(g_delay[i]);
    }

  if (g_verbose)
    {
      NS_LOG_UNCOND ("MyGetObservation: " << box);
    }

  return box;
}


/*
 * Reward function.
 *
 * Important:
 *   The reward is NOT recalculated from the current queue here.
 *   It is calculated immediately after executing the action in
 *   MyExecuteActions().
 *
 * This avoids mixing the reward with the next random traffic arrival.
 */
float
MyGetReward(void)
{
  if (g_verbose)
    {
      NS_LOG_UNCOND ("MyGetReward: " << g_lastReward
                     << " throughput=" << g_lastThroughput
                     << " rewardQueue=" << g_lastRewardQueue
                     << " totalDelay=" << g_lastTotalDelay
                     << " deadlineMisses=" << g_lastDeadlineMisses);
    }

  return g_lastReward;
}


/*
 * Extra info for debugging Python agents.
 *
 * rewardQueue:
 *   Queue length immediately after serving the selected user.
 *   This is the queue used for reward calculation.
 *
 * currentQueue:
 *   Current queue length when this info is requested.
 */
std::string
MyGetExtraInfo(void)
{
  float currentQueue = GetTotalQueue();
  float currentDelay = GetTotalDelay();
  uint32_t currentDeadlineMisses = GetDeadlineMisses();

  std::ostringstream info;
  info << "step=" << g_step
       << "|lastServedUser=" << g_lastServedUser
       << "|lastThroughput=" << g_lastThroughput
       << "|rewardQueue=" << g_lastRewardQueue
       << "|currentQueue=" << currentQueue
       << "|totalDelay=" << g_lastTotalDelay
       << "|currentDelay=" << currentDelay
       << "|deadlineMisses=" << g_lastDeadlineMisses
       << "|currentDeadlineMisses=" << currentDeadlineMisses
       << "|lastReward=" << g_lastReward;

  if (g_verbose)
    {
      NS_LOG_UNCOND ("MyGetExtraInfo: " << info.str());
    }

  return info.str();
}


/*
 * Execute received scheduling action.
 *
 * The action is interpreted as:
 *   action = selected user index
 *
 * Reward is calculated immediately after service:
 *   reward = served
 *            - 0.01 * totalQueueAfterService
 *            - 0.1 * totalDelayAfterService
 *            - 5.0 * deadlineMisses
 */
bool
MyExecuteActions(Ptr<OpenGymDataContainer> action)
{
  Ptr<OpenGymDiscreteContainer> discrete =
      DynamicCast<OpenGymDiscreteContainer> (action);

  if (!discrete)
    {
      NS_LOG_UNCOND ("MyExecuteActions: invalid action container");
      return false;
    }

  uint32_t selectedUser = discrete->GetValue();

  if (selectedUser >= userNum)
    {
      NS_LOG_UNCOND ("MyExecuteActions: selected user out of range: "
                     << selectedUser);
      return false;
    }

  g_lastServedUser = selectedUser;

  /*
   * Simplified service model:
   *   serviceRate = CQI * 2
   *
   * Actual served data:
   *   served = min(queue[selectedUser], serviceRate)
   */
  float serviceRate = g_cqi[selectedUser] * 2.0;
  float served = std::min(static_cast<float> (g_queue[selectedUser]),
                          serviceRate);

  g_queue[selectedUser] -= static_cast<uint32_t> (served);
  g_lastThroughput = served;

  for (uint32_t i = 0; i < userNum; i++)
    {
      if (i == selectedUser && g_queue[i] == 0)
        {
          g_delay[i] = 0;
        }
    }

  /*
   * Calculate reward immediately after service.
   *
   * This queue is after the selected user's data is transmitted,
   * but before the next random traffic arrival.
   */
  g_lastRewardQueue = GetTotalQueue();
  g_lastTotalDelay = GetTotalDelay();
  g_lastDeadlineMisses = GetDeadlineMisses();
  g_lastReward = g_lastThroughput
                 - 0.01 * g_lastRewardQueue
                 - 0.1 * g_lastTotalDelay
                 - 5.0 * g_lastDeadlineMisses;

  g_step++;

  if (g_verbose)
    {
      NS_LOG_UNCOND ("Selected user: " << selectedUser
                     << " cqi=" << g_cqi[selectedUser]
                     << " served=" << served
                     << " remainingQueue=" << g_queue[selectedUser]
                     << " rewardQueue=" << g_lastRewardQueue
                     << " totalDelay=" << g_lastTotalDelay
                     << " deadlineMisses=" << g_lastDeadlineMisses
                     << " reward=" << g_lastReward
                     << " step=" << g_step);
    }

  return true;
}


/*
 * Update channel quality and traffic arrival.
 *
 * This function generates the next environment state:
 *   - Markov CQI update for each user
 *   - new traffic arrival for each user's queue
 *   - delay increases for non-empty queues
 */
void
UpdateWirelessEnv()
{
  if (!g_rng)
    {
      g_rng = CreateObject<UniformRandomVariable> ();
    }

  for (uint32_t i = 0; i < userNum; i++)
    {
      int32_t delta = static_cast<int32_t> (g_rng->GetInteger(0, 4)) - 2;
      int32_t nextCqi = static_cast<int32_t> (g_cqi[i]) + delta;
      nextCqi = std::max<int32_t> (1, std::min<int32_t> (maxCqi, nextCqi));
      g_cqi[i] = static_cast<uint32_t> (nextCqi);

      uint32_t arrival = g_rng->GetInteger(0, 5);
      g_queue[i] = std::min(maxQueue, g_queue[i] + arrival);

      if (g_queue[i] > 0)
        {
          g_delay[i] = std::min(maxDelay, g_delay[i] + 1);
        }
      else
        {
          g_delay[i] = 0;
        }
    }
}


/*
 * Periodically notify Python agent of current state.
 *
 * Step meaning:
 *   1. UpdateWirelessEnv() prepares current state s_t.
 *   2. NotifyCurrentState() sends s_t to Python.
 *   3. Python returns action a_t.
 *   4. MyExecuteActions() executes a_t and calculates reward r_t.
 *
 * The next scheduled call will generate the next random CQI/arrival.
 */
void
ScheduleNextStateRead(double envStepTime, Ptr<OpenGymInterface> openGym)
{
  Simulator::Schedule (Seconds(envStepTime),
                       &ScheduleNextStateRead,
                       envStepTime,
                       openGym);

  if (g_step < g_maxSteps)
    {
      UpdateWirelessEnv();
    }

  openGym->NotifyCurrentState();
}


int
main (int argc, char *argv[])
{
  uint32_t simSeed = 1;
  double simulationTime = 20; // seconds
  double envStepTime = 0.5;   // seconds
  uint32_t openGymPort = 5555;

  CommandLine cmd;

  cmd.AddValue ("openGymPort",
                "Port number for OpenGym env. Default: 5555",
                openGymPort);

  cmd.AddValue ("simSeed",
                "Seed for random generator. Default: 1",
                simSeed);

  cmd.AddValue ("simTime",
                "Simulation time in seconds. Default: 20s",
                simulationTime);

  cmd.AddValue ("envStepTime",
                "Environment step interval in seconds. Default: 0.5s",
                envStepTime);

  cmd.AddValue ("verbose",
                "Print detailed C++ environment logs. Default: false",
                g_verbose);

  cmd.Parse (argc, argv);

  if (simulationTime <= 0.0 || envStepTime <= 0.0)
    {
      NS_FATAL_ERROR ("simTime and envStepTime must be positive");
    }

  g_maxSteps = std::max<uint32_t> (
      1,
      static_cast<uint32_t> (std::ceil (simulationTime / envStepTime)));

  if (g_verbose)
    {
      NS_LOG_UNCOND ("Ns3Env parameters:");
      NS_LOG_UNCOND ("--simulationTime: " << simulationTime);
      NS_LOG_UNCOND ("--openGymPort: " << openGymPort);
      NS_LOG_UNCOND ("--envStepTime: " << envStepTime);
      NS_LOG_UNCOND ("--maxSteps: " << g_maxSteps);
      NS_LOG_UNCOND ("--seed: " << simSeed);
      NS_LOG_UNCOND ("--userNum: " << userNum);
      NS_LOG_UNCOND ("--deadline: " << deadline);
    }

  RngSeedManager::SetSeed (1);
  RngSeedManager::SetRun (simSeed);

  g_rng = CreateObject<UniformRandomVariable> ();

  for (uint32_t i = 0; i < userNum; i++)
    {
      g_cqi[i] = g_rng->GetInteger(1, maxCqi);
    }

  /*
   * OpenGym environment.
   */
  Ptr<OpenGymInterface> openGym =
      CreateObject<OpenGymInterface> (openGymPort);

  openGym->SetGetActionSpaceCb (MakeCallback (&MyGetActionSpace));
  openGym->SetGetObservationSpaceCb (MakeCallback (&MyGetObservationSpace));
  openGym->SetGetGameOverCb (MakeCallback (&MyGetGameOver));
  openGym->SetGetObservationCb (MakeCallback (&MyGetObservation));
  openGym->SetGetRewardCb (MakeCallback (&MyGetReward));
  openGym->SetGetExtraInfoCb (MakeCallback (&MyGetExtraInfo));
  openGym->SetExecuteActionsCb (MakeCallback (&MyExecuteActions));

  Simulator::Schedule (Seconds(0.0),
                       &ScheduleNextStateRead,
                       envStepTime,
                       openGym);

  if (g_verbose)
    {
      NS_LOG_UNCOND ("Simulation start");
    }

  Simulator::Stop (Seconds (simulationTime));
  Simulator::Run ();

  if (g_verbose)
    {
      NS_LOG_UNCOND ("Simulation stop");
    }

  openGym->NotifySimulationEnd();

  Simulator::Destroy ();
}
