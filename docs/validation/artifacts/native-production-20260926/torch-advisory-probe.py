# Isolated reproduction of the class shape in pytorch/pytorch#149623.
# No user code is accepted by the serving API. This is not a full security proof.
import torch
@torch.jit.script
class Ignored:
    def __init__(self):
        self.count: int = 0
        self.items: list = []
print('compiled', torch.__version__)
