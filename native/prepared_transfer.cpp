// Small LibTorch bridge: current-stream completion and ownership-aware reuse.
#include <ATen/core/Tensor.h>
#include <c10/core/Event.h>
#include <c10/core/impl/VirtualGuardImpl.h>
#include <string>
static thread_local std::string last_error;
extern "C" {
const char* aimee_transfer_error() { return last_error.c_str(); }
void* aimee_event_new(const at::Tensor* tensor) {
  try { return new c10::Event(tensor->device().type()); }
  catch (const std::exception& e) { last_error = e.what(); return nullptr; }
}
int aimee_event_record(void* event, const at::Tensor* tensor) {
  try {
    c10::impl::VirtualGuardImpl guard(tensor->device().type());
    static_cast<c10::Event*>(event)->record(guard.getStream(tensor->device()));
    return 0;
  } catch (const std::exception& e) { last_error = e.what(); return -1; }
}
int aimee_event_wait(void* event) {
  try { static_cast<c10::Event*>(event)->synchronize(); return 0; }
  catch (const std::exception& e) { last_error = e.what(); return -1; }
}
void aimee_event_free(void* event) { delete static_cast<c10::Event*>(event); }
int aimee_copy_async(at::Tensor* destination, const at::Tensor* source) {
  try { destination->copy_(*source, true); return 0; }
  catch (const std::exception& e) { last_error = e.what(); return -1; }
}
size_t aimee_tensor_refs(const at::Tensor* tensor) { return tensor->use_count(); }
size_t aimee_storage_refs(const at::Tensor* tensor) { return tensor->storage().use_count(); }
}
#include <ATen/DLConvertor.h>
extern "C" {
void* aimee_tensor_import_dlpack(void* input) {
  try { return new at::Tensor(at::fromDLPack(static_cast<DLManagedTensor*>(input))); }
  catch (const std::exception& e) { last_error = e.what(); return nullptr; }
}
void* aimee_tensor_export_dlpack(const at::Tensor* tensor) {
  try { return at::toDLPack(*tensor); }
  catch (const std::exception& e) { last_error = e.what(); return nullptr; }
}
}
