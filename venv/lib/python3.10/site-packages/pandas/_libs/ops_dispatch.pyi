import numpy as np

def maybe_dispatch_ufunc_to_dunder_op(
    self, ufunc: np.ufunc, method: str, *inputs, **kwargs
): ...
