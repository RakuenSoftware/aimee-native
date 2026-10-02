import pathlib,json,hashlib
root=pathlib.Path('/opt/aimee/kernels');manifest=json.loads((root/'manifest.json').read_text());expected={'manifest.json'}
for item in manifest['kernels']:expected.update(item['files'])
files={p.name:p for p in root.iterdir() if p.is_file()}
assert set(files)==expected,{'unexpected':sorted(set(files)-expected),'missing':sorted(expected-set(files))}
package=pathlib.Path('/usr/local/lib/python3.12/dist-packages/aimee_vllm')
private=[str(p.relative_to(package)) for p in package.rglob('*') if p.is_file() and p.suffix in ('.py','.pyx','.c','.cpp','.cu','.hip') and p.name!='__init__.py']
assert not private,private
print(json.dumps({'status':'passed','kernel_count':len(manifest['kernels']),'kernel_file_count':len(files),'kernel_hashes':{n:hashlib.sha256(p.read_bytes()).hexdigest() for n,p in files.items()},'private_source_files':private,'package_files':sorted(p.name for p in package.iterdir() if p.is_file()),'scope':'Installed native package and manifest-referenced kernel bank; not resistance to binary reverse engineering'},indent=2))
