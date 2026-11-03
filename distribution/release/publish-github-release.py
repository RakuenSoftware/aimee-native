#!/usr/bin/env python3
"""Publish signed assets with the repository-scoped GitHub Actions token.

Use REST release IDs throughout: draft web URLs are temporary and release-list
indexes can lag creation. Never move a tag or replace published/mismatched assets.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.parse
import urllib.request

REPO = 'RakuenSoftware/aimee-native'


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def validate_metadata(release, tag, commit, expected):
    if release['tag_name'] != tag or release['target_commitish'] != commit:
        raise ValueError('existing release has a different target')
    return validate_assets(release, expected)


def validate_assets(release, expected):
    names = set()
    for asset in release['assets']:
        name = asset['name']
        if name not in expected or name in names:
            raise ValueError('unexpected or duplicate release asset')
        names.add(name)
        if asset['size'] != expected[name]['bytes']:
            raise ValueError('existing asset size mismatch: ' + name)
        if asset.get('digest') and asset['digest'] != 'sha256:' + expected[name]['sha256']:
            raise ValueError('existing asset digest mismatch: ' + name)
    return names


def choose_release(releases, tag, commit, notes):
    matches = [r for r in releases if r['tag_name'] == tag]
    if not matches:
        # GitHub may assign a temporary untagged URL/name to a new draft.
        matches = [r for r in releases if r['draft'] and r['name'] == 'Aimee Native ' + tag[1:]
                   and r['target_commitish'] == commit and (r.get('body') or '').strip() == notes.strip()]
    if len(matches) > 1:
        raise ValueError('ambiguous release drafts')
    return matches[0] if matches else None


def api(path, method='GET', body=None):
    command = ['gh', 'api', 'repos/' + REPO + '/' + path, '--method', method]
    if body is not None:
        command += ['--input', '-']
    return json.loads(subprocess.check_output(command, input=json.dumps(body).encode() if body is not None else None))


class NoUploadRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        # The authenticated upload stays at GitHub's fixed upload endpoint.
        return None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--public-key', type=Path, required=True)
    p.add_argument('--notes', type=Path, required=True)
    p.add_argument('--version', required=True)
    p.add_argument('--resume-tag', action='store_true', help='recover the existing tag from its release branch')
    p.add_argument('--stage-only', action='store_true', help='verify the draft without a workflow-authorized publish')
    a = p.parse_args()
    tag = 'v' + a.version
    allowed_ref = 'refs/heads/release/' + tag if a.resume_tag else 'refs/tags/' + tag
    if os.environ.get('GITHUB_REPOSITORY') != REPO or os.environ.get('GITHUB_REF') != allowed_ref:
        raise ValueError('publication requires the canonical release workflow')
    commit = subprocess.check_output(['git', 'rev-parse', 'refs/tags/' + tag + '^{commit}'], text=True).strip()
    if a.resume_tag:
        subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'HEAD'], check=True)
        # Recovery may change automation, never the signed payload or trust key.
        subprocess.run(['git', 'diff', '--exit-code', commit, 'HEAD', '--',
            'distribution/release/github/' + tag, 'distribution/release/public-keys'], check=True)
    else:
        assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == commit
    verifier = Path(__file__).with_name('release-bundle.py')
    def verify(folder):
        subprocess.run(['python3', str(verifier), 'verify', '--bundle', str(folder),
            '--public-key', str(a.public_key), '--expected-version', a.version], check=True)
    verify(a.bundle)
    expected = {f.name: {'bytes': f.stat().st_size, 'sha256': sha(f)} for f in a.bundle.iterdir()}
    pages = json.loads(subprocess.check_output(['gh', 'api', 'repos/' + REPO +
        '/releases?per_page=100', '--paginate', '--slurp', '-H', 'Cache-Control: no-cache']))
    notes = a.notes.read_text()
    release = choose_release([r for page in pages for r in page], tag, commit, notes)
    definition = dict(tag_name=tag, target_commitish=commit, name='Aimee Native ' + a.version, body=notes)
    if a.stage_only:
        if release is None:
            raise ValueError('staging requires an existing release')
        if release['draft'] and (release['target_commitish'] != commit or release['name'] != definition['name']
                               or (release.get('body') or '').strip() != notes.strip()):
            raise ValueError('staging requires the matching existing draft')
        if not release['draft'] and release['tag_name'] != tag:
            raise ValueError('published release has a different tag')
    if release is None:
        release = api('releases', 'POST', dict(definition, draft=True, prerelease=False))
    elif release['draft'] and not a.stage_only:
        release = api('releases/' + str(release['id']), 'PATCH', definition)
    release_id = release['id']
    print('Release ID:', release_id, 'draft:', release['draft'], flush=True)
    existing = validate_assets(release, expected) if a.stage_only else validate_metadata(release, tag, commit, expected)
    missing = sorted(set(expected) - existing)
    if missing and not release['draft']:
        raise ValueError('published release is incomplete; refusing to replace it')
    upload = urllib.request.build_opener(NoUploadRedirect())
    for name in missing:
        url = 'https://uploads.github.com/repos/' + REPO + '/releases/' + str(release_id) + '/assets?name=' + urllib.parse.quote(name, safe='')
        request = urllib.request.Request(url, data=(a.bundle / name).read_bytes(), method='POST',
            headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Content-Type': 'application/octet-stream',
                     'Accept': 'application/vnd.github+json', 'User-Agent': 'Aimee-Native-release'})
        with upload.open(request, timeout=300) as response:
            response.read()
        print('Uploaded:', name, flush=True)
    release = api('releases/' + str(release_id))
    names = validate_assets(release, expected) if a.stage_only else validate_metadata(release, tag, commit, expected)
    if names != set(expected):
        raise ValueError('release asset inventory is incomplete')
    with tempfile.TemporaryDirectory(prefix='aimee-release-download-') as folder:
        folder = Path(folder)
        for asset in release['assets']:
            # gh's HTTP client handles authenticated API redirects safely.
            with (folder / asset['name']).open('xb') as output:
                subprocess.run(['gh', 'api', 'repos/' + REPO + '/releases/assets/' + str(asset['id']),
                                '-H', 'Accept: application/octet-stream'], stdout=output, check=True)
        verify(folder)
    if a.stage_only:
        print('Verified release ready:', release['html_url'], 'draft:', release['draft'],
              'intended tag:', tag, 'commit:', commit)
        return
    if release['draft']:
        api('releases/' + str(release_id), 'PATCH', dict(definition, draft=False, prerelease=False, make_latest='true'))
    print('Published and download-verified: https://github.com/' + REPO + '/releases/tag/' + tag)


if __name__ == '__main__':
    main()
