"""Fixed source/thread hooks followed by the already CPU-tested core."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fixed_process_profile_v1 as core
from fixed_integration_v1 import install_role, require


def main():
    import hashlib
    require(hashlib.sha256(Path(core.__file__).read_bytes()).hexdigest()
            == '70c5ef4d50b2ac2859796eff3258c02b865f22ec9ed49ce70f98869296a4429c',
            'the fixed A62 core bytes differ')
    command = list(sys.argv[1:])
    roles = [role for role, path in core.PROGRAMS.items() if command and command[0] == str(path)]
    require(len(roles) == 1, 'target is outside the fixed three-role whitelist')
    role = roles[0]
    profiles = core.OWNED_EPISODE / 'profiles'
    profiles.mkdir(exist_ok=True)
    require(profiles == profiles.resolve(strict=True), 'owned profile directory has a symlink component')
    install_role(core, role)
    # Match normal `python original_script.py ...` sibling-import semantics.
    sys.path[0] = str(core.PROGRAMS[role].parent)
    core.run_role(role, command)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
