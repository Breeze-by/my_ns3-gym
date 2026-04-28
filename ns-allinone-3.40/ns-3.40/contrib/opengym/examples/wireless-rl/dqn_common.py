#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import random
from collections import deque

import numpy as np
import torch
import torch.nn as nn


USER_NUM = 5
STATE_DIM = USER_NUM * 2
ACTION_DIM = USER_NUM
CQI_MAX = 10.0
QUEUE_MAX = 100.0


def normalize_observation(obs):
    state = np.asarray(obs, dtype=np.float32).copy()
    if state.shape[0] != STATE_DIM:
        raise ValueError(f"Expected observation dim {STATE_DIM}, got {state.shape[0]}")

    state[0::2] /= CQI_MAX
    state[1::2] /= QUEUE_MAX
    return state


def split_observation(obs):
    obs = np.asarray(obs, dtype=np.float32)
    return obs[0::2], obs[1::2]


def parse_info(info):
    parsed = {}
    if not info:
        return parsed
    if isinstance(info, dict):
        return info

    for item in str(info).split("|"):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        try:
            number = float(value)
            if number.is_integer():
                number = int(number)
            parsed[key] = number
        except ValueError:
            parsed[key] = value

    return parsed


def jain_fairness(values):
    values = [float(value) for value in values]
    denominator = len(values) * sum(value * value for value in values)
    if denominator == 0:
        return 0.0
    return (sum(values) ** 2) / denominator


def summarize_rows(rows):
    if not rows:
        return {}

    rewards = [float(row["reward"]) for row in rows]
    throughputs = [float(row["lastThroughput"]) for row in rows]
    current_queues = [float(row["currentQueue"]) for row in rows]
    reward_queues = [float(row["rewardQueue"]) for row in rows]

    service_counts = [0 for _ in range(USER_NUM)]
    service_amounts = [0.0 for _ in range(USER_NUM)]
    for row in rows:
        user = int(row["lastServedUser"])
        if 0 <= user < USER_NUM:
            service_counts[user] += 1
            service_amounts[user] += float(row["lastThroughput"])

    summary = {
        "agent": rows[0]["agent"],
        "seed": rows[0]["seed"],
        "episode": rows[0]["episode"],
        "steps": len(rows),
        "average_reward": float(np.mean(rewards)),
        "cumulative_reward": float(rows[-1]["totalReward"]),
        "average_throughput": float(np.mean(throughputs)),
        "average_current_queue": float(np.mean(current_queues)),
        "average_reward_queue": float(np.mean(reward_queues)),
        "final_current_queue": float(current_queues[-1]),
        "final_reward_queue": float(reward_queues[-1]),
        "service_amount_fairness": jain_fairness(service_amounts),
    }

    for user in range(USER_NUM):
        summary[f"user{user}_served_count"] = service_counts[user]
        summary[f"user{user}_served_amount"] = service_amounts[user]

    return summary


class QNetwork(nn.Module):
    def __init__(self,
                 state_dim=STATE_DIM,
                 action_dim=ACTION_DIM,
                 hidden_size=64,
                 network_type="mlp"):
        super().__init__()
        self.network_type = network_type
        self.feature = nn.Sequential(
            nn.Linear(state_dim, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
        )

        if network_type == "dueling":
            self.value_head = nn.Linear(hidden_size, 1)
            self.advantage_head = nn.Linear(hidden_size, action_dim)
        elif network_type == "mlp":
            self.q_head = nn.Linear(hidden_size, action_dim)
        else:
            raise ValueError(f"Unknown network_type: {network_type}")

    def forward(self, x):
        features = self.feature(x)
        if self.network_type == "dueling":
            value = self.value_head(features)
            advantage = self.advantage_head(features)
            return value + advantage - advantage.mean(dim=1, keepdim=True)
        return self.q_head(features)


class ReplayBuffer:
    def __init__(self, capacity, seed):
        self.buffer = deque(maxlen=capacity)
        self.rng = random.Random(seed)

    def __len__(self):
        return len(self.buffer)

    def add(self, state, action, reward, next_state, done):
        self.buffer.append((state, int(action), float(reward), next_state, bool(done)))

    def sample(self, batch_size):
        batch = self.rng.sample(self.buffer, batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)
        return (
            np.asarray(states, dtype=np.float32),
            np.asarray(actions, dtype=np.int64),
            np.asarray(rewards, dtype=np.float32),
            np.asarray(next_states, dtype=np.float32),
            np.asarray(dones, dtype=np.float32),
        )


def select_dqn_action(model, state, epsilon, rng, device):
    if rng.random() < epsilon:
        return int(rng.integers(0, ACTION_DIM))

    with torch.no_grad():
        state_tensor = torch.as_tensor(state, dtype=torch.float32, device=device).unsqueeze(0)
        q_values = model(state_tensor)
        return int(torch.argmax(q_values, dim=1).item())


def heuristic_action_from_raw_obs(obs, strategy="max_service"):
    cqi, queue = split_observation(obs)

    if strategy == "greedy":
        score = cqi * queue
        if np.max(score) <= 0:
            score = cqi
        return int(np.argmax(score))

    if strategy == "max_queue":
        return int(np.argmax(queue))

    if strategy == "max_cqi":
        return int(np.argmax(cqi))

    if strategy == "max_service":
        service = np.minimum(queue, 2.0 * cqi)
        if np.max(service) <= 0:
            return int(np.argmax(cqi))
        return int(np.argmax(service))

    raise ValueError(f"Unknown heuristic strategy: {strategy}")


def make_synthetic_training_batch(batch_size, rng, strategy="max_service"):
    cqi = rng.integers(1, int(CQI_MAX) + 1, size=(batch_size, USER_NUM))
    queue = rng.integers(0, int(QUEUE_MAX) + 1, size=(batch_size, USER_NUM))

    raw_states = np.empty((batch_size, STATE_DIM), dtype=np.float32)
    raw_states[:, 0::2] = cqi
    raw_states[:, 1::2] = queue

    labels = []
    for row in raw_states:
        labels.append(heuristic_action_from_raw_obs(row, strategy=strategy))

    states = raw_states.copy()
    states[:, 0::2] /= CQI_MAX
    states[:, 1::2] /= QUEUE_MAX
    return states.astype(np.float32), np.asarray(labels, dtype=np.int64)


def build_step_row(agent, seed, episode, step, obs, action, reward, total_reward, done, info):
    cqi, queue = split_observation(obs)
    parsed_info = parse_info(info)
    row = {
        "episode": episode,
        "step": step,
        "agent": agent,
        "seed": seed,
        "action": int(action),
        "reward": float(reward),
        "totalReward": float(total_reward),
        "lastServedUser": int(parsed_info.get("lastServedUser", action)),
        "lastThroughput": float(parsed_info.get("lastThroughput", 0.0)),
        "rewardQueue": float(parsed_info.get("rewardQueue", np.sum(queue))),
        "currentQueue": float(parsed_info.get("currentQueue", np.sum(queue))),
        "done": bool(done),
        "info": str(info),
        "cqi": " ".join(str(int(value)) for value in cqi),
        "queue": " ".join(str(int(value)) for value in queue),
    }

    for user in range(USER_NUM):
        row[f"cqi{user}"] = int(cqi[user])
        row[f"queue{user}"] = int(queue[user])

    return row
