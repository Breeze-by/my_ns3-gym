#!/usr/bin/env python3

import subprocess
import sys
import tempfile
from pathlib import Path

import torch
import torch.nn.functional as F

from dqn_common import QNetwork, STATE_DIM


PROJECT_DIR = Path(__file__).resolve().parent
NS3_ROOT = PROJECT_DIR.parents[3]
EXPECTED_ENV = Path("/home/zhuyulab/miniconda3/envs/ns3gym")
CHECK_SEED = 4242


def check_environment():
    if Path(sys.prefix) != EXPECTED_ENV:
        raise RuntimeError(f"Activate conda environment ns3gym first; current prefix: {sys.prefix}")
    if EXPECTED_ENV not in Path(torch.__file__).parents:
        raise RuntimeError(f"PyTorch is outside ns3gym and may shadow its CUDA build: {torch.__file__}")
    if not torch.cuda.is_available():
        raise RuntimeError(f"CUDA is unavailable in PyTorch {torch.__version__} from {torch.__file__}")


def check_gpu():
    device = torch.device("cuda:0")
    model = QNetwork(network_type="dueling").to(device)
    optimizer = torch.optim.Adam(model.parameters())
    states = torch.zeros((2, STATE_DIM), device=device)
    labels = torch.tensor([0, 1], device=device)

    logits = model(states)
    loss = F.cross_entropy(logits, labels)
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()

    if not logits.is_cuda or not next(model.parameters()).is_cuda:
        raise RuntimeError("DQN inference or training did not run on CUDA")


def run_baseline(output_dir):
    subprocess.run(
        [
            sys.executable,
            str(PROJECT_DIR / "test.py"),
            "--agent",
            "greedy",
            "--seed",
            str(CHECK_SEED),
            "--simTime",
            "1",
            "--stepTime",
            "0.5",
            "--outputDir",
            str(output_dir),
            "--no-plot",
        ],
        cwd=PROJECT_DIR,
        check=True,
    )


def check_reproducibility():
    with tempfile.TemporaryDirectory(prefix="wireless-rl-check-") as temp_dir:
        root = Path(temp_dir)
        first = root / "first"
        second = root / "second"
        run_baseline(first)
        run_baseline(second)

        relative_paths = [
            Path("results") / f"greedy_seed{CHECK_SEED}.csv",
            Path("summaries") / f"greedy_seed{CHECK_SEED}_summary.csv",
        ]
        for relative_path in relative_paths:
            if (first / relative_path).read_bytes() != (second / relative_path).read_bytes():
                raise RuntimeError(f"Fixed-seed runs differ: {relative_path}")


def main():
    check_environment()
    print(f"Environment: {sys.prefix}")
    print(f"PyTorch: {torch.__version__} ({torch.__file__})")
    print(f"GPU: {torch.cuda.get_device_name(0)}")

    check_gpu()
    print("GPU DQN forward/backward: passed")

    subprocess.run([str(NS3_ROOT / "ns3"), "build", "wireless-rl"], cwd=NS3_ROOT, check=True)
    print("ns-3 build: passed")

    check_reproducibility()
    print(f"Fixed-seed smoke test ({CHECK_SEED}): passed")


if __name__ == "__main__":
    main()
