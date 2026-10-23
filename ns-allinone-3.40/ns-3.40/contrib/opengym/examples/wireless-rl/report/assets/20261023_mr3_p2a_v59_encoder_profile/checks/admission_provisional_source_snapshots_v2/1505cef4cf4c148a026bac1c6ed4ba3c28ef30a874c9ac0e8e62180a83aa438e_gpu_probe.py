"""Execute only the prospectively declared P1C tensor forward/backward probe.

This is a capacity/interface check on a saved received-information fixture.
It creates no simulator, optimizer, policy rollout, update, or checkpoint.
"""

import argparse
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter


def _snapshot(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("kind") == "observation":
                return row["payload"]
    raise ValueError("declared fixture contains no policy observation")


def run(plan, root):
    if os.environ.get("PYTHONNOUSERSITE") != "1" or os.environ.get("PYTHONPATH"):
        raise RuntimeError("use isolated ns3gym with PYTHONNOUSERSITE=1 and no ROS PYTHONPATH")
    if Path(sys.executable).resolve().parent != Path(plan["python"]).resolve().parent:
        raise RuntimeError("the probe requires the declared ns3gym interpreter")
    if plan["kind"] != "mr3-p1c-gpu-forward-backward-plan-v1":
        raise ValueError("unexpected probe plan")
    if plan["batches"] != [1, 8, 32] or plan["optimizer_steps"] != 0:
        raise ValueError("the declared budget is three forward/backward calls, no updates")
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    import numpy as np
    import torch

    from .model import MR3ActorCritic
    from .observation import TENSOR_SCHEMA, encode_snapshot

    if importlib.metadata.version("torch") != plan["versions"]["torch"]:
        raise RuntimeError("torch version differs from the declared probe")
    if importlib.metadata.version("gymnasium") != plan["versions"]["gymnasium"]:
        raise RuntimeError("gymnasium version differs from the declared probe")
    torch.set_num_threads(1)
    torch.manual_seed(plan["seed"])
    torch.cuda.manual_seed_all(plan["seed"])
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    device = torch.device(plan["device"])
    if device.type != "cuda" or not torch.cuda.is_available():
        raise RuntimeError("the declared CUDA device is unavailable")
    path = root / plan["snapshot_log"]
    snapshot = _snapshot(path)
    observation = encode_snapshot(snapshot)
    model = MR3ActorCritic().to(device)
    results = []
    for batch in plan["batches"]:
        inputs = {key: torch.from_numpy(np.repeat(value[None], batch, axis=0)).to(device)
                  for key, value in observation.items()}
        model.zero_grad(set_to_none=True)
        torch.cuda.reset_peak_memory_stats(device)
        torch.cuda.synchronize(device)
        started = perf_counter()
        logits, values = model(inputs)
        legal = inputs["action_mask"].bool()
        choices = legal.long().argmax(dim=-1, keepdim=True)
        loss = (-torch.log_softmax(logits, dim=-1).gather(1, choices).mean()
                + values.square().mean())
        loss.backward()
        torch.cuda.synchronize(device)
        elapsed = perf_counter() - started
        gradients = [parameter.grad for parameter in model.parameters()]
        finite = all(gradient is not None and torch.isfinite(gradient).all().item()
                     for gradient in gradients)
        norm = sum(gradient.square().sum().item() for gradient in gradients
                   if gradient is not None) ** 0.5
        checks = {
            "legal_logits_finite": torch.isfinite(logits[legal]).all().item(),
            "illegal_logits_negative_infinity": torch.isneginf(logits[~legal]).all().item(),
            "values_finite": torch.isfinite(values).all().item(),
            "gradients_finite": finite, "nonzero_gradient": norm > 0,
        }
        if not all(checks.values()):
            raise RuntimeError(f"CUDA tensor/gradient checks failed: {checks}")
        results.append({
            "batch": batch, "logit_shape": list(logits.shape), "value_shape": list(values.shape),
            "loss": loss.item(), "gradient_l2_norm": norm, "checks": checks,
            "forward_backward_wall_sec": elapsed,
            "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated(device),
        })
    return {
        "kind": "mr3-p1c-gpu-interface-probe-not-policy-training", "success": True,
        "source_freeze": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "python": sys.executable, "torch": torch.__version__, "cuda": torch.version.cuda,
        "device": str(device), "device_name": torch.cuda.get_device_name(device),
        "seed": plan["seed"], "tensor_schema": TENSOR_SCHEMA,
        "snapshot_digest": snapshot["digest"],
        "snapshot_log_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "optimizer_steps": 0, "simulator_episodes": 0, "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    plan_bytes = arguments.plan.read_bytes()
    plan = json.loads(plan_bytes)
    root = Path(__file__).resolve().parents[1]
    with arguments.output.open("x") as handle:
        try:
            result = run(plan, root)
        except Exception as error:
            json.dump({"success": False, "error": repr(error),
                       "plan_sha256": hashlib.sha256(plan_bytes).hexdigest()}, handle,
                      sort_keys=True, allow_nan=False, indent=2)
            handle.write("\n")
            raise
        result["plan_sha256"] = hashlib.sha256(plan_bytes).hexdigest()
        json.dump(result, handle, sort_keys=True, allow_nan=False, indent=2)
        handle.write("\n")
    print(json.dumps({"success": result["success"], "output": str(arguments.output),
                      "parameter_count": result["parameter_count"]}, sort_keys=True))


if __name__ == "__main__":
    main()
