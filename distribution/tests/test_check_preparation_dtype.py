import importlib.util,json,pathlib,unittest
p=pathlib.Path(__file__).with_name('check_preparation_dtype.py');spec=importlib.util.spec_from_file_location('dtype_check',p);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class PreparedDtype(unittest.TestCase):
    def job(self,dtype='torch.float32',evaluated=106):return json.dumps({'event':'prepared','computation':{'compute_dtype':dtype,'evaluated_tokens':evaluated}})
    def test_accepts_actual_fp32_job(self):self.assertEqual(len(module.prepared_jobs('model loading\n'+self.job())),1)
    def test_rejects_empty_or_only_reused_jobs(self):
        for logs in ('',self.job(evaluated=0)):
            with self.assertRaises(ValueError):module.prepared_jobs(logs)
    def test_rejects_any_bf16_job_in_window(self):
        with self.assertRaises(ValueError):module.prepared_jobs(self.job()+'\n'+self.job('torch.bfloat16'))

if __name__=='__main__':unittest.main()
