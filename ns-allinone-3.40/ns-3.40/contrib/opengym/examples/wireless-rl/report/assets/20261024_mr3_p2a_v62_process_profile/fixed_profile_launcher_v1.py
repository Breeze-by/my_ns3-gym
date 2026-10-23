"""Fixed V62 open101/eight-step diagnostic; no policy/scientific credit."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fixed_integration_v1 import HERE, ROOT, RUN, W, install_supervisor, require
LEARNER_PYTHON = Path('/home/zhuyulab/miniconda3/envs/ns3gym/bin/python')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    args = parser.parse_args(argv)
    require(Path(sys.executable).resolve() == LEARNER_PYTHON.resolve(),
            'fixed ns3gym benchmark interpreter required; ROS roles remain system Python')
    path = Path(__file__).resolve()
    require(path.is_relative_to(ROOT), 'only a new canonical frozen diagnostic launcher may execute')
    git = lambda *v: subprocess.check_output(['git', *v], cwd=ROOT)
    require(git('rev-parse', 'HEAD').decode().strip() == args.freeze
            == git('rev-parse', 'origin/main').decode().strip() and not git('status', '--porcelain'),
            'exact clean pushed diagnostic source freeze required')
    for source in [*HERE.glob('*.py'), HERE / 'base_source_pins_v1.json', HERE / 'fixed_process_profile_v1.py']:
        require(source.is_relative_to(ROOT) and
                git('show', args.freeze+':'+str(source.relative_to(ROOT))) == source.read_bytes(),
                'fixed integration source differs from its new freeze')
    pins = json.loads((HERE / 'base_source_pins_v1.json').read_text())
    for literal, item in pins['sources'].items():
        source = Path(literal)
        raw = source.read_bytes()
        require(source.is_relative_to(ROOT) and len(raw) == item['bytes']
                and __import__('hashlib').sha256(raw).hexdigest() == item['sha256']
                and git('show', args.freeze+':'+str(source.relative_to(ROOT))) == raw,
                'actual new freeze production source differs')
    RUN.mkdir(exist_ok=False)
    (RUN / 'launcher.json').open('x').write(json.dumps(dict(freeze=args.freeze,
        actual_argv=[value.decode() for value in Path('/proc/self/cmdline').read_bytes().split(b'\0') if value],
        diagnostic_profile='mr3-p2a-v62-open101-8step-cprofile-v1',
        diagnostic_only=True, scientific_qualification=False, capacity_qualified=False,
        nav2_parameter_readback_taken=False), indent=2)+'\n')
    sys.path.insert(0, str(W))
    install_supervisor()
    from mr3_learning import benchmark
    command = ['--workers', '1', '--schedule', 'open:101', '--steps', '8',
               '--base-domain', '230', '--base-port', '15901', '--output-root', str(RUN), '--run-id', 'native',
               '--work-wall-seconds', '1500', '--close-reserve-seconds', '120',
               '--safety-contract', 'mr3-reach-v1', '--seed-rule', 'exact-point-bridge-v2',
               '--start-graph-rule', 'point-attachment-3x3-v1', '--reach-geometry-rule', 'cone-support-v2']
    sys.argv = [str(W / 'mr3_learning/benchmark.py'), *command]
    return benchmark.main()


if __name__ == '__main__':
    raise SystemExit(main())
