"""Pass a systemd database credential to the private publisher, without a shell."""
import os
import pathlib
import sys


def main():
    if len(sys.argv) < 2 or not os.path.isabs(sys.argv[1]):
        raise SystemExit('absolute publisher executable required')
    credential = pathlib.Path(os.environ['CREDENTIALS_DIRECTORY']) / 'database'
    with credential.open('rb') as source:
        value = source.read(16385)
    if not value or len(value) > 16384 or b'\0' in value or b'\n' in value:
        raise SystemExit('invalid database credential')
    environment = dict(os.environ, AIMEE_IMAGE_DATABASE_URL=value.decode())
    os.execve(sys.argv[1], sys.argv[1:], environment)


if __name__ == '__main__':
    main()
