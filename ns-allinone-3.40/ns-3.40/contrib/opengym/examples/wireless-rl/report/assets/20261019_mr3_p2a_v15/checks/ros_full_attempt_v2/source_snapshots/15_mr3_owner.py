"""One local Nav2 goal owner per ROS domain, shared by both execution modes."""

import fcntl
import os
from pathlib import Path


def acquire_navigation_owner():
    domain = int(os.environ.get("ROS_DOMAIN_ID", "0"))
    path = Path(f"/tmp/mr3-navigation-owner-{os.getuid()}-{domain}.lock")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    handle = os.fdopen(descriptor, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise RuntimeError(f"Nav2 already has a goal owner in ROS domain {domain}") from None
    return handle
