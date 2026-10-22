"""Run only artificial resource fixtures; never instantiate execution/model roles."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
W = BASE / "overlay_workspace_v1/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
os.chdir(W)
sys.path.insert(0, str(W))
os.environ.update(CUDA_VISIBLE_DEVICES="", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
                 OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
import pytest
from mr3_learning import ppo, reach_preparation as prep

calls = []
original_popen = subprocess.Popen

def readonly_git(argv, *args, **kwargs):
    if not isinstance(argv, (list, tuple)) or len(argv) < 2 or argv[0] != "git" or argv[1] not in {
            "ls-files", "show", "rev-parse", "status"}:
        raise AssertionError("CPU fixture forbids subprocess: " + repr(argv))
    calls.append(list(argv))
    return original_popen(argv, *args, **kwargs)

def forbidden(*args, **kwargs):
    raise AssertionError("CPU fixture crossed model/native/GPU boundary")

with contextlib.ExitStack() as stack:
    stack.enter_context(patch.object(subprocess, "Popen", side_effect=readonly_git))
    for owner, name in ((ppo, "Supervisor"), (ppo, "MaskablePPO"), (ppo, "resource_sample"),
                        (ppo.torch.cuda, "is_available"), (ppo.torch.cuda, "init")):
        stack.enter_context(patch.object(owner, name, side_effect=forbidden))
    rc = pytest.main([str(W / "mr3_learning/tests/test_reach_engineering_block.py"),
                      "-q", "-p", "no:cacheprovider", "--basetemp", str(BASE / "pytest_tmp_v1")])
metadata = {"schema": "mr3-resource-profile-artificial-cpu-v1", "passed": rc == 0,
    "pytest_returncode": int(rc), "fixture_only": True,
    "engineering_charge_seconds": "0", "resource_amounts_synthetic": True,
    "new_real_engineering_ceiling_selected": False,
    "native_or_world_or_model_or_gpu_started": False,
    "overlay_workspace": str(prep.WORKSPACE), "overlay_module": prep.__file__,
    "readonly_git_subprocesses": calls}
with (BASE / "overlay_cpu_result_v1.json").open("x") as stream:
    json.dump(metadata, stream, indent=2)
    stream.write("\n")
print(json.dumps(metadata))
raise SystemExit(rc)
