"""Keep managed read-only observers from outliving their experiment owner."""
import ctypes
import os
import signal
import sys


def bind_to_owner():
    owner = int(os.environ.get('P3B5_OBSERVER_OWNER_PID', os.getppid()))
    if owner <= 1 or os.getppid() != owner:
        raise RuntimeError('Read-only observer owner already exited')
    if sys.platform != 'linux':
        raise RuntimeError('Observer owner binding requires Linux')
    libc = ctypes.CDLL(None, use_errno=True)
    # SIGKILL also closes an observer stuck in native DDS initialization.
    if libc.prctl(1, int(signal.SIGKILL), 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    # The owner can disappear between the check and PR_SET_PDEATHSIG.
    if os.getppid() != owner:
        raise RuntimeError('Read-only observer owner exited during binding')
