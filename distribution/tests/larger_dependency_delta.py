"""Reconcile retained dependency and notice evidence, without granting release approval."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    artifacts = root / 'docs/validation/artifacts'
    references = []
    def read(relative):
        path = artifacts / relative
        references.append(dict(path=str(path.relative_to(root)), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        return json.loads(path.read_text())
    baseline = read('native-production-20260926/inventory-r13.json')
    current = read('larger-runtime-inventory-20260928/inventory.json')
    previous = read('current-dependency-review-20260928/review.json')
    disposition = read('native-live-release-20260926/package-review.json')
    notices = read('larger-notice-audit-20260928/report.json')
    # Compare actual metadata and license-file hashes, not only version strings.
    def packages(value):
        return {(p['name'], p['version']): p for p in value['python_packages']}
    old, new = packages(baseline), packages(current)
    if set(old) != set(new):
        raise ValueError('Python package versions changed')
    changes = {str(k): dict(previous=old[k], current=new[k]) for k in old if old[k] != new[k]}
    if baseline['os_packages'] != current['os_packages']:
        raise ValueError('OS inventory changed')
    for name, key in [('Cargo.lock', 'native_cargo_lock_sha256'), ('distribution/launcher/Cargo.lock', 'launcher_cargo_lock_sha256')]:
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != previous[key]:
            raise ValueError(f'Cargo graph changed: {name}')
    rows = {}
    for model, data in notices['packages'].items():
        review = read(f'larger-normal-package-review-20260928/{model}/review.json')
        if data['manifest_sha256'] != review['source_manifest_sha256']:
            raise ValueError('notice audit targets a different package')
        preserved, model_specific = [], []
        for notice in data['notices']:
            key = notice['path']
            if key.startswith('licenses/model-'):
                model_specific.append(notice)
            elif previous['packaged_notices'].get(key) != notice['sha256']:
                raise ValueError(f'changed common notice: {key}')
            else:
                preserved.append(key)
        if len(preserved) != 6:
            raise ValueError('missing common dependency notices')
        rows[model] = dict(artifact_set_sha256=review['artifact_set_sha256'], common_notices_unchanged=preserved,
                           model_specific_notices=model_specific)
    report = dict(status='delta_review_complete', scope=__doc__, python_packages=len(new),
                  os_packages=len(current['os_packages']), python_metadata_changes=changes, packages=rows,
                  known_limitations=disposition['dependency_review']['known_limitations'],
                  public_redistribution_cleared=False, release_approved=False,
                  interpretation='Unchanged dependency versions, license metadata, lockfiles and common notice bytes preserve the earlier controlled-infrastructure review scope. Model-specific notices are separately identified. This does not fulfill the still-outstanding external source/notice distribution obligations or create a new vulnerability scan.',
                  evidence=references)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as f:
        json.dump(report, f, indent=2)
        f.write('\n')
    print(json.dumps(dict(status=report['status'], python_metadata_changes=len(changes), packages=list(rows))))


if __name__ == '__main__':
    main()
