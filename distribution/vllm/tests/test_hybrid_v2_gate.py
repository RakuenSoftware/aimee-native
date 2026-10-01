import unittest

from vllm.v1.worker.gpu.model_states.mamba_hybrid import MambaHybridModelState
from aimee_vllm.worker import require_v2_request_slots


class HybridV2GateTests(unittest.TestCase):
    def test_live_hybrid_requires_v1_until_upstream_supplies_request_slots(self):
        hybrid = object.__new__(MambaHybridModelState)
        require_v2_request_slots(object(), False)
        with self.assertRaisesRegex(RuntimeError, "set v2_model_runner=false"):
            require_v2_request_slots(type("Runner", (), {"model_state": hybrid})(), True)
        require_v2_request_slots(type("Runner", (), {"model_state": object()})(), True)


if __name__ == "__main__":
    unittest.main()
