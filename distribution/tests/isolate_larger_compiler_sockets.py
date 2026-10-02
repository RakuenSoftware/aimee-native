"""Lab migration: each compiler owns its socket lifecycle independently."""
from pathlib import Path
import json
import os
import subprocess

ROOT = Path('/opt/aimee-large-release-validation/assembly/compiler-socket-isolation')
SERVICE = Path('/opt/aimee-native-compiler/larger-20260928')


def main():
    ROOT.mkdir(mode=0o700, exist_ok=False)
    names = ['aimee-native-' + profile + '-validation.service' for profile in ('gemma26', 'qwen27')]
    subprocess.run(['systemctl', 'stop', *names], check=True)
    for profile, name in zip(('gemma26', 'qwen27'), names):
        unit = Path('/etc/systemd/system') / name
        worker = SERVICE / (profile + '-worker.json')
        old = unit.read_text(); raw = worker.read_bytes(); data = json.loads(raw)
        runtime = 'aimee-native-' + profile + '-validation'
        socket = '/run/' + runtime + '/compile.sock'
        assert data['resident_socket'] == '/run/aimee-native-compiler/' + profile + '.sock'
        (ROOT / (name + '.before')).write_text(old)
        (ROOT / (profile + '-worker.before.json')).write_bytes(raw)
        new = old.replace('After=aimee-native-compiler.service', 'After=local-fs.target')
        new = new.replace('[Service]\n', '[Service]\nRuntimeDirectory=' + runtime + '\nRuntimeDirectoryMode=0700\n')
        new = new.replace('/run/aimee-native-compiler/' + profile + '.sock', socket)
        new = new.replace('/run/aimee-native-compiler', '/run/' + runtime)
        assert 'aimee-native-compiler.service' not in new and '/run/aimee-native-compiler' not in new
        unit.write_text(new)
        data['resident_socket'] = socket
        meta = worker.stat(); stage = worker.with_suffix('.next')
        stage.write_text(json.dumps(data) + '\n'); stage.chmod(meta.st_mode & 0o777)
        os.chown(stage, meta.st_uid, meta.st_gid); stage.replace(worker)
        (ROOT / (name + '.after')).write_text(new)
        (ROOT / (profile + '-worker.after.json')).write_text(json.dumps(data) + '\n')
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'start', *names], check=True)
    print(subprocess.check_output(['systemctl', 'show', *names, '-p', 'Id', '-p', 'ActiveState', '-p', 'MainPID'], text=True))


if __name__ == '__main__':
    main()
