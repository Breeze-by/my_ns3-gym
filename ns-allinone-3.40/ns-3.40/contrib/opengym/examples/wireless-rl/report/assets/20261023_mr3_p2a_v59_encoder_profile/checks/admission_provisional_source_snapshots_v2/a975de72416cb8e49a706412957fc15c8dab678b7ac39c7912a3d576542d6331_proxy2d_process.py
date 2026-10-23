"""Linux pidfds through libc when the conda Python lacks optional os APIs."""
import ctypes
import os
import platform
import signal


def pidfd_open(pid):
    if hasattr(os, "pidfd_open"):
        return os.pidfd_open(pid)
    libc = ctypes.CDLL(None, use_errno=True)
    if platform.machine() != "x86_64":
        raise RuntimeError("unreviewed pidfd syscall ABI")
    # Verified against this host's asm/unistd_64.h (__NR_pidfd_open).
    operation = libc.syscall
    operation.restype = ctypes.c_long
    descriptor = operation(ctypes.c_long(434), ctypes.c_int(pid), ctypes.c_uint(0))
    if descriptor < 0:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number))
    return descriptor


def pidfd_send_signal(descriptor, number):
    if hasattr(signal, "pidfd_send_signal"):
        return signal.pidfd_send_signal(descriptor, number)
    libc = ctypes.CDLL(None, use_errno=True)
    if platform.machine() != "x86_64":
        raise RuntimeError("unreviewed pidfd syscall ABI")
    # Verified against this host's asm/unistd_64.h (__NR_pidfd_send_signal).
    operation = libc.syscall
    operation.restype = ctypes.c_long
    if operation(ctypes.c_long(424), ctypes.c_int(descriptor), ctypes.c_int(number),
                 ctypes.c_void_p(), ctypes.c_uint(0)) < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
