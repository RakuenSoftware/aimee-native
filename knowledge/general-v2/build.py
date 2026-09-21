"""Build a larger factual public KB from pinned v1 + GeoNames city snapshots."""
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent

def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()

def build():
    manifest = json.loads((ROOT/'sources/manifest.json').read_text())
    for name, meta in manifest.items():
        assert hashlib.sha256((ROOT/'sources'/name).read_bytes()).hexdigest() == meta['sha256']
    base_path = ROOT.parent/'general-v1/records.json'
    base = json.loads(base_path.read_text())
    records = base['records'][:]
    source = manifest['cities500.zip']
    fields = ['geonameid','name','asciiname','alternate_names','latitude','longitude','feature_class',
              'feature_code','country_code','cc2','admin1','admin2','admin3','admin4','population',
              'elevation','dem','timezone','modified']
    with zipfile.ZipFile(ROOT/'sources/cities500.zip') as z:
        with z.open('cities500.txt') as f:
            for values in csv.reader(io.TextIOWrapper(f,encoding='utf-8'),delimiter='\t',quoting=csv.QUOTE_NONE):
                assert len(values) == len(fields)
                row = dict(zip(fields, values))
                assert row['geonameid'].isdigit() and row['feature_class'] == 'P'
                assert -90 <= float(row['latitude']) <= 90 and -180 <= float(row['longitude']) <= 180
                key = f"place {row['name']} {row['country_code'] or 'unassigned'} {row['geonameid']}"
                content = (f"GeoNames lists place {row['name']} (ID {row['geonameid']}): "
                           f"country code {row['country_code'] or 'unassigned'}; "
                           f"latitude {row['latitude']}; longitude {row['longitude']}; "
                           f"administrative codes {row['admin1'] or 'unspecified'}/{row['admin2'] or 'unspecified'}; "
                           f"population {row['population']}; time zone {row['timezone'] or 'unspecified'}. "
                           f"The source record was modified on {row['modified']}.")
                semantic = dict(row, domain='geonames')
                semantic['alternate_names'] = sorted(set(filter(None,row['alternate_names'].split(','))))
                metadata = dict(semantic=semantic, provenance=dict(source_url=source['url'],
                    source_sha256=source['sha256'], retrieved_at=source['retrieved_at'],
                    license='CC BY 4.0', attribution='GeoNames', locator=dict(geonameid=row['geonameid'])))
                revision = hashlib.sha256(canonical(dict(key=key,content=content,metadata=metadata))).hexdigest()
                records.append(dict(namespace=base['namespace'],id='geonames.'+row['geonameid'],revision=revision,
                    scope=dict(type='global',value='_global'),key=key,content=content,kind='fact',tier='L3',
                    confidence=1,lifecycle='active',metadata=metadata))
    records.sort(key=lambda r:r['id'])
    assert len({r['id'] for r in records}) == len(records)
    result = dict(base,records=records,source='Pinned general-v1 plus GeoNames populated places; public reference release v2')
    encoded = canonical(result)+b'\n'
    (ROOT/'records.json').write_bytes(encoded)
    summary = dict(records=len(records),previous_records=len(base['records']),geonames_records=len(records)-len(base['records']),
        canonical_json_bytes=len(encoded),content_bytes=sum(len(r['content'].encode()) for r in records),
        sha256=hashlib.sha256(encoded).hexdigest(),base_sha256=hashlib.sha256(base_path.read_bytes()).hexdigest(),
        synthetic_records=0,read_contracts=0)
    (ROOT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary

if __name__ == '__main__':
    print(json.dumps(build(),indent=2))
