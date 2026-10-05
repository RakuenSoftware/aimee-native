"""Invoke the one installed model plugin selected by the deployment config."""
import argparse
import importlib
import json
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True)
    args=parser.parse_args()
    config=json.loads(Path(args.config).read_bytes())
    package={
        'gemma4-12b':'aimee_gemma4_12b',
        'gemma4-26b':'aimee_gemma4_26b',
        'qwen3-8-27b':'aimee_qwen3_8_27b',
    }.get(config.get('adapter'))
    if package is None or config.get('python_module')!=package:
        raise RuntimeError('deployment must select its dedicated model plugin')
    sys.argv=[package,'--config',args.config]
    importlib.import_module(package+'.cli').main()


if __name__=='__main__':
    main()
