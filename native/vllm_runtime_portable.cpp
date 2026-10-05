// Thin CPython ABI bridge to the installed public torch API. No ATen linkage,
// GPU runtime linkage, storage implementation, or memory encoder lives here.
#include <Python.h>
#include <cstdint>
#include <cstddef>

namespace {
struct GIL { PyGILState_STATE state = PyGILState_Ensure(); ~GIL() { if (PyErr_Occurred()) PyErr_Print(); PyGILState_Release(state); } };
struct Ref {
  PyObject* p;
  explicit Ref(PyObject* v=nullptr):p(v) {}
  ~Ref() { Py_XDECREF(p); }
  Ref(const Ref&)=delete;
  PyObject* release() { auto* v=p;p=nullptr;return v; }
};
PyObject* ops() {
  // Each worker imports once. The interpreter owns the module for its lifetime.
  static PyObject* module=nullptr;
  if (!module) module=PyImport_ImportModule("aimee_native_runtime.runtime_ops");
  return module;
}
PyObject* invoke(const char* name, PyObject* args) {
  Ref owned(args);if (!args) return nullptr;
  auto* module=ops();if (!module) return nullptr;
  Ref fn(PyObject_GetAttrString(module,name));
  return fn.p ? PyObject_CallObject(fn.p,args) : nullptr;
}
bool done(PyObject* value) { Ref result(value);return result.p!=nullptr; }
}
extern "C" {
void* aimee_rt_host(size_t bytes) noexcept {
  GIL gil;return invoke("host",Py_BuildValue("(K)",(unsigned long long)bytes));
}
void* aimee_rt_device(size_t bytes,int device) noexcept {
  GIL gil;return invoke("device",Py_BuildValue("(Ki)",(unsigned long long)bytes,device));
}
bool aimee_rt_stream(void* tensor,void** stream) noexcept {
  GIL gil;Ref value(invoke("stream",Py_BuildValue("(O)",(PyObject*)tensor)));
  if (!value.p) return false;
  *stream=PyLong_AsVoidPtr(value.p);return !PyErr_Occurred();
}
void* aimee_rt_data(void* tensor) noexcept {
  GIL gil;Ref value(PyObject_CallMethod((PyObject*)tensor,"data_ptr",nullptr));
  return value.p ? PyLong_AsVoidPtr(value.p) : nullptr;
}
void* aimee_rt_upload(void* tensor,int device) noexcept {
  GIL gil;return invoke("upload",Py_BuildValue("(Oi)",(PyObject*)tensor,device));
}
bool aimee_rt_upload_range(void* host,void* device,size_t offset,size_t bytes) noexcept {
  GIL gil;return done(invoke("upload_range",Py_BuildValue("(OOKK)",(PyObject*)host,(PyObject*)device,(unsigned long long)offset,(unsigned long long)bytes)));
}
bool aimee_rt_wait(void* tensor) noexcept {
  GIL gil;return done(invoke("wait",Py_BuildValue("(O)",(PyObject*)tensor)));
}
void* aimee_rt_view(void* tensor,size_t heads,size_t positions,size_t width,size_t offset) noexcept {
  GIL gil;return PyObject_CallMethod((PyObject*)tensor,"as_strided","(KKK)(KKK)K",
    (unsigned long long)heads,(unsigned long long)positions,(unsigned long long)width,
    (unsigned long long)(positions*width),(unsigned long long)width,1ULL,(unsigned long long)(offset/2));
}
void aimee_rt_free(void* tensor) noexcept { GIL gil;Py_XDECREF((PyObject*)tensor); }
void* aimee_rt_python(void* const* tensors,const size_t* layers,const bool* values,size_t n) noexcept {
  GIL gil;Ref result(PyDict_New());if (!result.p) return nullptr;
  for (size_t i=0;i<n;++i) {
    Ref key(Py_BuildValue("(KO)",(unsigned long long)layers[i],values[i] ? Py_True : Py_False));
    if (!key.p || PyDict_SetItem(result.p,key.p,(PyObject*)tensors[i])<0) return nullptr;
  }
  return result.release();
}
int aimee_decode_bf16(const void* input,const void* positions,void* output,size_t words,size_t exception_offset,
 size_t exceptions,uint64_t table0,uint64_t table1,void* stream,int device) noexcept {
  GIL gil;return done(invoke("decode",Py_BuildValue("(KKKKKKKKKi)",
    (unsigned long long)(uintptr_t)input,(unsigned long long)(uintptr_t)positions,(unsigned long long)(uintptr_t)output,
    (unsigned long long)words,(unsigned long long)exception_offset,(unsigned long long)exceptions,
    (unsigned long long)table0,(unsigned long long)table1,(unsigned long long)(uintptr_t)stream,device))) ? 0 : -1;
}
}
