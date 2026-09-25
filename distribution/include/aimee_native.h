/* Private runtime integration ABI. Distributed documentation excludes storage encoding. */
#ifndef AIMEE_NATIVE_H
#define AIMEE_NATIVE_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif
/* ABI 1 uses the current LibTorch/DLPack bridge. A ggml bridge is not yet certified.
 * Handles must be used serially by their owning session. No simultaneous apply.
 * Returned DLPack managed tensors transfer ownership to the caller; invoke their
 * deleter exactly once. Retain the session/output until device consumption is
 * complete. Changes in selected records/revision require a new handle.
 * Activation validates prepared state before serving. Apply never encodes text.
 */
uint32_t aimee_native_abi_version(void);
const char *aimee_native_error(void); /* borrowed, thread-local; copy before next call */
void *aimee_native_open(const char *activation_json);
const char *aimee_native_metadata(void *session); /* borrowed until session closes */
void *aimee_native_apply(void *session);
const char *aimee_native_result_metadata(void *result); /* borrowed until result freed */
void *aimee_native_result_tensor(void *result, size_t layer, bool value);
void aimee_native_result_free(void *result);
void aimee_native_close(void *session);
#ifdef __cplusplus
}
#endif
#endif
