"""Optional public-source numeric rendering ablation.
Preserve the original semantic/source values. Render finite NIST quantities in
plain decimal notation, exactly (Decimal, never binary floats). This is a KB
compiler operation, not domain logic or learning in the model adapter.
"""
import argparse,copy,hashlib,json
from decimal import Decimal,InvalidOperation
from pathlib import Path

def plain(value):
    try:
        number=Decimal(value.replace(' ',''))
        if not number.is_finite():return value
        result=format(number,'f')
        assert Decimal(result)==number
        return result
    except InvalidOperation:return value

def normalize(row):
    s=row.get('metadata',{}).get('semantic',{})
    if s.get('domain')!='nist':return row
    value,uncertainty=plain(s['value']),plain(s['uncertainty'])
    text=f"The 2022 CODATA value of the constant {s['subject']} is {value} {s['unit']}. Its standard uncertainty is {uncertainty}."
    if text==row['content']:return row
    r=copy.deepcopy(row);r['content']=text
    r['metadata']['rendering']={'version':'finite-decimal-v1','source_revision':row['revision']}
    raw=json.dumps(dict(key=r['key'],content=r['content'],metadata=r['metadata']),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    r['revision']=hashlib.sha256(raw).hexdigest()
    return r

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    source=json.loads(a.input.read_text());changed=[normalize(r) for r in source['records'] if normalize(r)!=r]
    a.output.write_text(json.dumps(changed,ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps(dict(changed_records=len(changed),bytes=a.output.stat().st_size)))
