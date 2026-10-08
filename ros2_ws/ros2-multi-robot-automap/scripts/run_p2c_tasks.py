#!/usr/bin/env python3
"""Reuse the strict single-cell owner with an independent P2C cohort namespace."""
from pathlib import Path
from run_p3c5_audit import main

if __name__=='__main__':
    raise SystemExit(main(Path(__file__).with_name('p2c_integration_manifest.json'), 'p2c'))
