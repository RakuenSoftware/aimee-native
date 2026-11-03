"""GPU mechanism tests with independently computed target-position RoPE keys."""
import unittest
import torch
from types import SimpleNamespace
from transformers import Qwen3Config
from scoped_cache import ScopedCache


class Model(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.parameter = torch.nn.Parameter(torch.zeros(1, device='cuda'))
        self.config = Qwen3Config(num_hidden_layers=2, num_attention_heads=2,
                                 num_key_value_heads=2, hidden_size=16, head_dim=8,
                                 use_sliding_window=False)
        self.model = SimpleNamespace(rotary_emb=self.rotary)

    def rotary(self, x, pos):
        freq = 1.0/(1000000.0**(torch.arange(0,8,2,device='cuda').float()/8))
        angles = pos.float()[...,None]*freq
        angles = torch.cat((angles,angles),-1)
        return angles.cos(), angles.sin()


def rotate(raw, position, model):
    c,s=model.rotary(raw, position[None])
    return raw*c[:,None]+torch.cat((-raw[...,4:],raw[...,:4]),-1)*s[:,None]


class InjectionTests(unittest.TestCase):
    def test_direct_target_position_and_immutable_history(self):
        model=Model(); engine=ScopedCache(model)
        torch.manual_seed(71)
        bank_raw=[torch.randn(1,2,19,8,device='cuda') for _ in range(2)]
        bank=engine.wrap([(rotate(k,torch.arange(19,device='cuda'),model), k+1) for k in bank_raw])
        saved=[(k.clone(),v.clone()) for k,v in engine.pairs(bank)]
        for h in [128,1024,4096]:
            history=engine.wrap([(torch.randn(1,2,h,8,device='cuda'),torch.randn(1,2,h,8,device='cuda')) for _ in range(2)])
            original=[(k.clone(),v.clone()) for k,v in engine.pairs(history)]
            joined=engine.attach(history,bank)
            for i,((jk,jv),(hk,hv)) in enumerate(zip(engine.pairs(joined),engine.pairs(history))):
                torch.testing.assert_close(jk[...,:h,:],hk,rtol=0,atol=0)
                torch.testing.assert_close(jv[...,:h,:],hv,rtol=0,atol=0)
                expected=rotate(bank_raw[i],torch.arange(h,h+19,device='cuda'),model)
                torch.testing.assert_close(jk[...,h:,:],expected,rtol=2e-6,atol=2e-6)
                torch.testing.assert_close(jv[...,h:,:],saved[i][1],rtol=0,atol=0)
                torch.testing.assert_close(hk,original[i][0],rtol=0,atol=0)
            # Advancing the temporary task wrapper must not append to its parent.
            joined.update(torch.zeros(1,2,1,8,device='cuda'),torch.zeros(1,2,1,8,device='cuda'),0)
            self.assertEqual(history.get_seq_length(),h)
        for actual,expected in zip(engine.pairs(bank),saved):
            for a,e in zip(actual,expected): torch.testing.assert_close(a,e,rtol=0,atol=0)


if __name__=='__main__':
    unittest.main()
