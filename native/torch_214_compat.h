// Build-only compatibility for tch 0.26 against the installed Torch 2.14.
// Torch removed these four deprecated aliases; tch's generated bindings still
// mention them. Preserve their semantics using the supported linalg operations.
// The Qwen adapter itself does not call these deprecated entry points.
#pragma once
#include <torch/torch.h>
namespace torch {
inline Tensor cholesky(const Tensor& x, bool upper) { return at::linalg_cholesky(x, upper); }
inline Tensor& cholesky_out(Tensor& out, const Tensor& x, bool upper) { return at::linalg_cholesky_out(out, x, upper); }
inline auto qr(const Tensor& x, bool some) { return at::linalg_qr(x, some ? "reduced" : "complete"); }
inline auto qr_out(Tensor& q, Tensor& r, const Tensor& x, bool some) { return at::linalg_qr_out(q, r, x, some ? "reduced" : "complete"); }
}
