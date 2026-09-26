"""Remove only an owned, inactive Unix socket before a supervised restart."""
import argparse
import errno
import os
import socket
import stat


def recover(path):
    try:
        node = os.lstat(path)
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(node.st_mode) or node.st_uid != os.geteuid() or stat.S_IMODE(node.st_mode) != 0o600:
        raise ValueError('unexpected control endpoint; refusing cleanup')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
        probe.settimeout(1)
        try:
            probe.connect(path)
        except OSError as error:
            if error.errno != errno.ECONNREFUSED:
                raise
        else:
            raise RuntimeError('control endpoint is still active')
    current = os.lstat(path)
    if (current.st_dev, current.st_ino) != (node.st_dev, node.st_ino):
        raise RuntimeError('control endpoint changed during recovery')
    os.unlink(path)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('path')
    recover(p.parse_args().path)
