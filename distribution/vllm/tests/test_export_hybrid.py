import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import torch
from aimee_vllm.hybrid import HybridPrefix

path=Path(__file__).resolve().parents[3]/'benchmarks/native_addressing/export_hybrid.py'
spec=importlib.util.spec_from_file_location('hybrid_export',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class HybridExportTests(unittest.TestCase):
    def fixture(self, directory):
        root=Path(directory);model=root/'model';prepared=root/'prepared';model.mkdir();prepared.mkdir()
        c={'layer_types':['full_attention','linear_attention'],'num_key_value_heads':2,'head_dim':4,
           'linear_num_key_heads':2,'linear_num_value_heads':4,'linear_key_head_dim':2,
           'linear_value_head_dim':3,'linear_conv_kernel_dim':4}
        config=json.dumps(c).encode();(model/'config.json').write_bytes(config)
        from tokenizers import Tokenizer,models
        Tokenizer(models.WordLevel({'foo':0,'bar':1})).save(str(model/'tokenizer.json'))
        identity=module.digest(b'aimee-complete-hybrid-v1revision'+b'\0'+config+(model/'tokenizer.json').read_bytes())
        data=torch.arange(32,dtype=torch.bfloat16).view(torch.uint8).numpy().tobytes()
        (prepared/'native.pack').write_bytes(b'\0'*4096+data)
        conv=torch.arange(80,dtype=torch.float32).reshape(1,20,4)
        recurrent=torch.arange(24,dtype=torch.float32).reshape(1,4,2,3)
        payload=conv.numpy().tobytes()+recurrent.numpy().tobytes();digest=module.digest(payload)
        layouts=[];offset=0
        for part,t in [('conv',conv),('recurrent',recurrent)]:
            n=t.numel()*t.element_size();layouts.append({'layer':1,'part':part,'dtype':'f32','shape':list(t.shape),'offset':offset,'bytes':n});offset+=n
        r={'version':1,'bytes':len(payload),'sha256':digest,'payload':digest+'.rnn.bin','layouts':layouts}
        (prepared/r['payload']).write_bytes(payload)
        entry={'offset':4096,'bytes':len(data),'sha256':module.digest(data),'tokens':[0,1],
               'dtype':'bf16','layouts':[{'layer':0,'shape':[1,2,2,4],'offset':0,'elements':16}], 'recurrent':r}
        (prepared/'index.json').write_text(json.dumps({'version':1,'model':identity,'entries':{'base':entry}}))
        return root,model,prepared,data

    def test_export_keeps_base_keys_and_binds_lossless_recurrence(self):
        with tempfile.TemporaryDirectory() as directory:
            root,model,prepared,data=self.fixture(directory);destination=root/'export'
            result=module.export(prepared,'base',model,'revision',False,'content','',destination)
            self.assertEqual((destination/'compact.pack').read_bytes()[4096:4096+len(data)],data)
            hybrid=HybridPrefix(destination,result['hybrid_state'],result['model'],result['key'])
            self.assertEqual((destination/hybrid.spec['recurrent']['payload']).stat().st_ino,(prepared/hybrid.spec['recurrent']['payload']).stat().st_ino)
            self.assertEqual(hybrid.spec['positioning'],'native-prefix-absolute-v1')
            self.assertEqual(hybrid.spec['encoder_weight_profile'],'bf16')
            self.assertEqual(hybrid.parts[1,'recurrent'].dtype,torch.float32)
            if os.environ.get('AIMEE_STORE_LIBRARY'):
                import ctypes
                from aimee_vllm.store import PreparedStore
                store=PreparedStore(ctypes.CDLL(os.environ['AIMEE_STORE_LIBRARY']),{**result,'byte_budget':4096,'lossless_transport':False})
                try:
                    self.assertEqual(store.metadata['positions'],2)
                    self.assertEqual(store.host_reservation_bytes(),896)
                    self.assertEqual(store.device_bytes(1),400)
                    self.assertEqual(store.staging_bytes(1),0)
                    self.assertEqual(store.reservation_bytes(1),400)
                finally:store.close()
            with self.assertRaises(FileExistsError):
                module.export(prepared,'base',model,'revision',False,'content','',destination)

    def test_wrong_weight_profile_and_corrupt_attention_fail_before_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root,model,prepared,_=self.fixture(directory);destination=root/'export'
            with self.assertRaisesRegex(ValueError,'profile'):
                module.export(prepared,'base',model,'revision',True,'content','',destination)
            self.assertFalse(destination.exists())
            with (prepared/'native.pack').open('r+b') as f:f.seek(4096);f.write(b'X')
            with self.assertRaisesRegex(ValueError,'attention payload'):
                module.export(prepared,'base',model,'revision',False,'content','',destination)
            self.assertFalse(destination.exists())


if __name__=='__main__':unittest.main()
