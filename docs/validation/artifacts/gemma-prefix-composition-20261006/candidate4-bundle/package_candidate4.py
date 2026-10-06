"""Private complete review bundle; no installation or publication."""
from pathlib import Path
import hashlib, zipfile, csv, io, base64, json
root=Path(__file__).parent
old=root/'aimee_native_runtime-0.3.2+gemma.prefix.candidate3-cp312-cp312-linux_x86_64.whl'
assert hashlib.sha256(old.read_bytes()).hexdigest()=='ce14f2abe92479142c4208194dc2cb1fa28faf11f9df39b3f15133e6acff6f94'
client=root/'target/release/aimee-model-client'
assert hashlib.sha256(client.read_bytes()).hexdigest()=='47583282d2278741ded4183df7707183855366a72760eeca2df876fbaa82a3ce'
version='0.3.2+gemma.prefix.candidate4'
out=root/('aimee_native_runtime-'+version+'-cp312-cp312-linux_x86_64.whl')
files={}
with zipfile.ZipFile(old) as z:
    names=[n for n in z.namelist() if n.endswith('/aimee-model-client')]
    assert len(names)==1,names
    clientname=names[0]
    for n in z.namelist():
        if n.endswith('/RECORD'):continue
        data=z.read(n)
        if n.endswith('/METADATA'):data=data.replace(b'Version: 0.3.2+gemma.prefix.candidate3',b'Version: 0.3.2+gemma.prefix.candidate4')
        if n==clientname:data=client.read_bytes()
        files[n.replace('candidate3.dist-info','candidate4.dist-info')]=data
record='aimee_native_runtime-'+version+'.dist-info/RECORD'
rows=[(n,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(d).digest()).decode().rstrip('='),str(len(d))) for n,d in sorted(files.items())]
rows.append((record,'',''));buf=io.StringIO();csv.writer(buf,lineterminator='\n').writerows(rows);files[record]=buf.getvalue().encode()
with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_DEFLATED) as z:
    for n,d in sorted(files.items()):
        info=zipfile.ZipInfo(n);info.compress_type=zipfile.ZIP_DEFLATED
        info.external_attr=(0o100755 if n==clientname else 0o100644)<<16
        z.writestr(info,d)
receipt={'status':'passed','version':version,'wheel':out.name,'wheel_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'client_sha256':hashlib.sha256(client.read_bytes()).hexdigest(),'base_wheel_sha256':hashlib.sha256(old.read_bytes()).hexdigest(),'source_archive_sha256':'1e507f3b83701f3d1f1c2eb533077322901d786d2a21d98f3287a7d7b95e4009','delta':'bundled model client, version metadata and RECORD only; compiled Python/kernel/license bytes unchanged','scope':'private review bundle; not deployed or signed; GPU candidate3 proof remains separate'}
with (root/'candidate4-packaging-receipt.json').open('x') as f:json.dump(receipt,f,indent=2)
print(json.dumps(receipt,indent=2))
