// ATen/CPython ABI glue only. Rust owns activation sequencing and tensor layout.
#include <ATen/ATen.h>
#include <c10/core/impl/VirtualGuardImpl.h>
#include <torch/csrc/autograd/python_variable.h>
extern "C" {
void* aimee_rt_host(size_t bytes) noexcept {
  try { return new at::Tensor(at::empty({static_cast<int64_t>(bytes / 2)}, at::TensorOptions().dtype(at::kBFloat16).device(at::kCPU).pinned_memory(true))); }
  catch (...) { return nullptr; }
}
void* aimee_rt_device(size_t bytes, int device) noexcept {
  try { return new at::Tensor(at::empty({static_cast<int64_t>(bytes / 2)}, at::TensorOptions().dtype(at::kBFloat16).device(at::Device(at::kCUDA, device)))); }
  catch (...) { return nullptr; }
}
bool aimee_rt_stream(void* tensor, void** stream) noexcept {
  try { auto device=static_cast<at::Tensor*>(tensor)->device(); c10::impl::VirtualGuardImpl guard(device.type()); *stream = guard.getStream(device).native_handle(); return true; }
  catch (...) { return false; }
}
void* aimee_rt_data(void* tensor) noexcept { return static_cast<at::Tensor*>(tensor)->data_ptr(); }
void* aimee_rt_upload(void* tensor, int device) noexcept {
  try { return new at::Tensor(static_cast<at::Tensor*>(tensor)->to(at::Device(at::kCUDA, device), true, false)); }
  catch (...) { return nullptr; }
}
bool aimee_rt_upload_range(void* host, void* device, size_t offset, size_t bytes) noexcept {
  try {
    static_cast<at::Tensor*>(device)->narrow(0,offset/2,bytes/2).copy_(
        static_cast<at::Tensor*>(host)->narrow(0,offset/2,bytes/2),true);
    return true;
  } catch (...) { return false; }
}
bool aimee_rt_wait(void* tensor) noexcept {
  try {
    auto device = static_cast<at::Tensor*>(tensor)->device();
    c10::impl::VirtualGuardImpl guard(device.type());
    guard.getStream(device).synchronize();
    return true;
  } catch (...) { return false; }
}
void* aimee_rt_view(void* tensor, size_t heads, size_t positions, size_t width, size_t offset) noexcept {
  try { return new at::Tensor(static_cast<at::Tensor*>(tensor)->as_strided(
      {static_cast<int64_t>(heads), static_cast<int64_t>(positions), static_cast<int64_t>(width)},
      {static_cast<int64_t>(positions*width), static_cast<int64_t>(width), 1}, static_cast<int64_t>(offset/2))); }
  catch (...) { return nullptr; }
}
void aimee_rt_free(void* tensor) noexcept { delete static_cast<at::Tensor*>(tensor); }
// GIL required. Return a NEW reference; the bridge explicitly transfers ownership.
void* aimee_rt_python(void* const* tensors, const size_t* layers, const bool* values, size_t n) noexcept {
  PyObject* result = PyDict_New();
  if (!result) return nullptr;
  try {
    for (size_t i=0; i<n; ++i) {
      PyObject* key=Py_BuildValue("(KO)", static_cast<unsigned long long>(layers[i]), values[i] ? Py_True : Py_False);
      PyObject* tensor=THPVariable_Wrap(*static_cast<at::Tensor*>(tensors[i]));
      if (!key || !tensor) { Py_XDECREF(key); Py_XDECREF(tensor); Py_DECREF(result); return nullptr; }
      int status=PyDict_SetItem(result,key,tensor); Py_DECREF(key); Py_DECREF(tensor);
      if (status<0) { Py_DECREF(result); return nullptr; }
    }
    return result;
  } catch (...) { Py_DECREF(result); PyErr_SetString(PyExc_RuntimeError,"native tensor wrapping failed"); return nullptr; }
}
}
