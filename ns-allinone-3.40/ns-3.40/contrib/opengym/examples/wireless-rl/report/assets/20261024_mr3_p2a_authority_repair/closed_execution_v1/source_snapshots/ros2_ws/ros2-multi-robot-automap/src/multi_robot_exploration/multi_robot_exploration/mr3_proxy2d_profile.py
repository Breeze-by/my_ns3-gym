"""Opt-in profiling that preserves the wrapped entry point's exit semantics."""

import cProfile
from pathlib import Path


def run_profiled(operation, output: Path):
    """Claim a new profile, run once, and propagate its return or exception."""
    with output.open("xb"):
        pass
    profiler = cProfile.Profile()
    profiler.enable()
    try:
        return operation()
    finally:
        profiler.disable()
        profiler.dump_stats(output)
