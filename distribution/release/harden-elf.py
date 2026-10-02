#!/usr/bin/env python3
"""Remove avoidable reverse-engineering metadata from a release ELF artifact."""
import argparse
from pathlib import Path
import shutil
import subprocess


FORBIDDEN_SECTIONS = ('.debug_', '.symtab', '.comment', '.note.gnu.build-id', '.gnu_debuglink', '.gnu_debugdata', '.GCC.command.line', '.llvm_addrsig', '.note.go.buildid', '.note.rustc')


def sections(path):
    return subprocess.check_output(['readelf', '-S', str(path)], text=True)


def harden(path):
    path = path.resolve()
    if path.read_bytes()[:4] != b'\x7fELF':
        raise ValueError(f'not an ELF artifact: {path}')
    strip = shutil.which('strip')
    objcopy = shutil.which('objcopy')
    if not strip or not objcopy:
        raise RuntimeError('binutils strip and objcopy are required for release hardening')
    subprocess.run([strip, '--strip-unneeded', str(path)], check=True)
    subprocess.run([
        objcopy,
        '--remove-section=.comment',
        '--remove-section=.note.gnu.build-id',
        '--remove-section=.gnu_debuglink',
        '--remove-section=.gnu_debugdata',
        '--remove-section=.GCC.command.line',
        '--remove-section=.llvm_addrsig',
        '--remove-section=.note.go.buildid',
        '--remove-section=.note.rustc',
        str(path),
    ], check=True)
    table = sections(path)
    leaked = [name for name in FORBIDDEN_SECTIONS if name in table]
    if leaked:
        raise ValueError(f'release metadata sections retained in {path.name}: {leaked}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact', nargs='+', type=Path)
    args = parser.parse_args()
    for artifact in args.artifact:
        harden(artifact)
