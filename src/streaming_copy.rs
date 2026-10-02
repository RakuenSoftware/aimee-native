//! Optional non-temporal writes for large pinned-output gathers. Capability is
//! detected at activation. Each writing thread fences before GPU DMA submission.
pub struct Streaming {
    _private: (),
}
impl Streaming {
    pub fn new() -> Option<Self> {
        #[cfg(target_arch = "x86_64")]
        if std::is_x86_feature_detected!("avx2") {
            return Some(Self { _private: () });
        }
        None
    }
    pub fn copy(&self, source: &[u8], destination: &mut [u8]) {
        assert_eq!(source.len(), destination.len());
        #[cfg(target_arch = "x86_64")]
        unsafe {
            copy_avx2(source.as_ptr(), destination.as_mut_ptr(), source.len());
        }
        #[cfg(not(target_arch = "x86_64"))]
        destination.copy_from_slice(source);
    }
    pub fn finish(&self) {
        #[cfg(target_arch = "x86_64")]
        unsafe {
            std::arch::x86_64::_mm_sfence();
        }
    }
}
#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx2")]
unsafe fn copy_avx2(mut src: *const u8, mut dst: *mut u8, mut len: usize) {
    use std::arch::x86_64::*;
    unsafe {
        // Destination alignment is required by streaming stores. Preserve edge
        // bytes and never touch bytes outside the caller's exact output range.
        while len > 0 && (dst as usize) & 31 != 0 {
            dst.write(src.read());
            src = src.add(1);
            dst = dst.add(1);
            len -= 1;
        }
        while len >= 128 {
            let a = _mm256_loadu_si256(src.cast());
            let b = _mm256_loadu_si256(src.add(32).cast());
            let c = _mm256_loadu_si256(src.add(64).cast());
            let d = _mm256_loadu_si256(src.add(96).cast());
            _mm256_stream_si256(dst.cast(), a);
            _mm256_stream_si256(dst.add(32).cast(), b);
            _mm256_stream_si256(dst.add(64).cast(), c);
            _mm256_stream_si256(dst.add(96).cast(), d);
            src = src.add(128);
            dst = dst.add(128);
            len -= 128;
        }
        while len >= 32 {
            _mm256_stream_si256(dst.cast(), _mm256_loadu_si256(src.cast()));
            src = src.add(32);
            dst = dst.add(32);
            len -= 32;
        }
        std::ptr::copy_nonoverlapping(src, dst, len);
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn streaming_preserves_misaligned_extents_and_guards() {
        let Some(copy) = Streaming::new() else { return };
        for size in [0, 1, 31, 32, 33, 127, 128, 129, 512, 4096, 65536] {
            for offset in 0..64 {
                let source: Vec<u8> = (0..size).map(|i| (i * 73 + 19) as u8).collect();
                let mut destination = vec![0xa5; size + 128];
                copy.copy(&source, &mut destination[offset..offset + size]);
                copy.finish();
                assert_eq!(&destination[offset..offset + size], source.as_slice());
                assert!(
                    destination[..offset]
                        .iter()
                        .chain(destination[offset + size..].iter())
                        .all(|&v| v == 0xa5)
                );
            }
        }
    }
}
