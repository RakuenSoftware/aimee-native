#[cfg(all(feature = "torch", not(feature = "native-client")))]
pub mod adapter;
#[cfg(feature = "torch")]
pub mod model;
pub mod tokens;
pub mod transport;

pub mod knowledge;

pub mod memory_encoding;

#[cfg(feature = "torch")]
pub mod prepared_memory;

pub mod native_packing;

pub mod prepared_files;

pub mod native_compression;

#[cfg(feature = "torch")]
pub mod compact_memory;

#[cfg(feature = "torch")]
pub mod prepared_transfer;

pub mod streaming_copy;

#[cfg(feature = "torch")]
pub mod native_ffi;

#[cfg(any(feature = "preparation-service", not(any(feature = "native-client", feature = "vllm-client"))))]
pub mod preparation_cache;

mod native_format;
pub mod native_store;

#[cfg(feature = "vllm-client")]
pub mod native_store_ffi;

#[cfg(feature = "vllm-client")]
pub mod vllm_runtime;

pub mod device_cache;

#[cfg(feature = "vllm-runtime")]
mod native_runtime;

#[cfg(feature = "preparation-service")]
mod preparation_reuse;

#[cfg(any(feature = "preparation-service", feature = "vllm-runtime"))]
pub mod native_transport_codec;

#[cfg(any(feature = "preparation-service", feature = "vllm-runtime"))]
mod native_transport;
