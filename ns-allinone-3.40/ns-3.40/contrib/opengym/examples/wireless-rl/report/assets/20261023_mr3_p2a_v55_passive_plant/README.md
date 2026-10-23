# V55 finite passive pair driver candidate

This directory is `/tmp` preparation only. No compiler, Gazebo/World, model,
robot episode, original telemetry consumer or training has been run by it.
Root owns installation, actual CPU checks, admission, commit/push and execution.

Install `run_passive_pair_v1.py`, `make_scope_v1.py` and
`test_run_passive_pair_v1.py` into canonical
`report/assets/20261023_mr3_p2a_v55_passive_plant/` without changing older assets.
The diagnostic C++/generator are the independent plant owner's files.

The driver reuses `reach_execution` for the real wrapper/CPP wait and
`preparation.identity` for actual identity capture. The small existing
`proxy2d_process` pidfd implementation signals only a same-start, observed direct
CPP child of its fresh private wrapper session. It does not instantiate a
Supervisor, ROS Node, actor, reward, learning environment or model.

After root's final actual build, create an exclusive proposed scope, using the
actual latest prepared spec and native manifest, for example:

```bash
rtk proxy /usr/bin/python3 -B report/assets/20261023_mr3_p2a_v55_passive_plant/make_scope_v1.py \
  --prepared-spec /ABS/A55/prepared_worlds_v3/spec_v1.json \
  --build-manifest /ABS/A55/checks/build_manifest_v2.json \
  --output /tmp/mr3_p2a_v55_scope_proposed_v1.json
```

Default `admitted:false` blocks all physical submission. Root may use `--admit`
only after the real final build, focused CPU/source checks and review of that
exact resource scope, writing the new canonical `A55/scope_v1.json` exclusively.
The maker records existing bytes; it never compiles, regenerates worlds, rewrites
the plant spec, fabricates a build receipt or invokes the driver.

The compiler actual wait is the existing `reach_execution --scope cpu` receipt;
its exact direct g++ argv must match the manifest's `build_entry.compiler_argv`,
CPP/header source bindings, `-o` target and ELF digest. `/tmp` ELF is not falsely
required to be a Git file: the committed build manifest, exact actual receipt,
ELF SHA and canonical lossless gzip mapping bind it. ELF and resolved linked
library objects are also included in the physical wrappers' before/after hashes.
Shared-library `/lib` aliases resolve to real objects before comparison.

New driver/C++/generator/import chain, old production/model/paired-header source
files, spec/worlds/scope/build manifest/build entry/canonical gzip must match the
new CLI Git freeze. Original production seven plus model/header/drive also match
old `1fa55bc56d5bb9e230d4b397f962d83b1604b278`. Installed ground and linked system
libraries have exact byte pins, without an invented old-Git claim.

Only after root's new commit/push and exact 40-character execution freeze:

```bash
rtk proxy /usr/bin/python3 -B report/assets/20261023_mr3_p2a_v55_passive_plant/run_passive_pair_v1.py --freeze EXACT40
```

Exclusive driver output is `/tmp/mr3_p2a_v55_driver_v1`. The driver creates the
`arms` parent, but the C++ owns exclusive leaf creation at `arms/quick50` and
`arms/direct-world`. Exactly these two arms run sequentially, once each, with
600 s native cooperative work, 45 s settle plus 310 s hold and 355000 fixed
1 ms steps. No sampling replay/CSV consumer is added. The driver checks only the
small native summary, early/late identity, actual rc/wait and declared completion
receipt. The sampled `within_R_observed` is a measurement and never determines
execution PASS or permission for the second arm.

The single engineering charge starts immediately before the first wrapper Popen
and ends at the final real wrapper wait: **all inter-arm gaps and metadata count**.
Nested case waits are retained but not added. Entry/post metadata spans are
separate. Entry U90357.3610697996018 / C120000, reservation1800. Any overrun is
fully charged and FAIL; there is no hard OS real-time or fabricated exit promise.

At 720 s outer time per arm (600 work plus setup/drain allowance), interruption,
or 20 s remaining in the continuous pair allocation, only observed own CPP gets
pidfd INT, then TERM after10 s, KILL after another10 s. The real owned wrapper
is still waited/reaped; interruptions do not abandon it. A missing/unreadable
identity is an error, matching Z remains present. Remaining pair wall below720 s
prevents a new arm and is explicitly FAIL, without retry or refund.

`GAZEBO_MASTER_URI=http://127.0.0.1:11555` is fixed in both the C++ and clean child
environment. Exclusive bind checks occur initially and between arms; reuseaddr
permits prior TIME_WAIT but rejects a live listener. A live unrelated service
causes failure; it is never signalled. Normal native code uses no external
processes, only Gazebo's own master thread. CPP ownership and port release are
checked before the next arm.

Every case saves command, real wrapper/CPP identities, partial summary, actual
returncode, signals/errors and complete source bindings. The final pair summary
retains all failures and expenses; root must later bind actual root-tool reap,
observe its ancestor using actual driver `sys.argv[0]` (not an invented index),
fresh-check all saved identities, and close/archive the small evidence. Policy
budgets, twelveEP/thirtyroles, 95% and safety gates remain unchanged.

Focused CPU command (root runs once with exact source-bound actual-wait receipt):

```bash
rtk proxy /usr/bin/python3 -B -m unittest discover \
  -s report/assets/20261023_mr3_p2a_v55_passive_plant \
  -p test_run_passive_pair_v1.py -v
```

Six tiny fixtures cover unadmitted/bad-budget rejection, whole Git byte mismatch,
interrupted fake-child wait/partial rc/no retry, full pair gap/overrun charges,
and a valid baseline R excess plus wrong-identity rejection. They create only
synthetic small temporary files; no real child, compiler or World is created.
