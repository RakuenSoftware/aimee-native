//! Experimental lossless BF16 transport. Encoding is offline; all 16 bits survive.
//! A 12-bit common code carries sign/mantissa and one of 15 exponent symbols.
//! Escapes carry the original word. This is not a tokenizer-ID representation.
use rayon::prelude::*;
#[derive(Clone)]
pub struct Encoded {
    pub payload: Vec<u8>,
    pub table: [u8; 16],
    pub words: usize,
    pub exceptions: usize,
    pub exception_offset: usize,
    pub exception_positions: Vec<usize>,
}
impl Encoded {
    pub fn encode(input: &[u16]) -> Self {
        assert!(input.len() <= u32::MAX as usize);
        let mut counts = [0usize; 256];
        for &v in input {
            counts[((v >> 7) & 255) as usize] += 1;
        }
        let mut symbols: Vec<_> = (0u16..256).collect();
        symbols.sort_by_key(|&s| (std::cmp::Reverse(counts[s as usize]), s));
        let mut table = [0u8; 16];
        let mut codes = [15u16; 256];
        for (i, &e) in symbols.iter().take(15).enumerate() {
            table[i] = e as u8;
            codes[e as usize] = i as u16;
        }
        let code_bytes = (input.len() * 12).div_ceil(8);
        let exception_offset = (code_bytes + 16).next_multiple_of(8);
        let mut payload = vec![0u8; exception_offset];
        let mut exceptions = 0;
        let mut exception_positions = Vec::new();
        for (i, &v) in input.iter().enumerate() {
            let e = codes[((v >> 7) & 255) as usize];
            let code = (v & 127) | ((v >> 8) & 128) | (e << 8);
            let b = i * 3 / 2;
            if i % 2 == 0 {
                payload[b] = code as u8;
                payload[b + 1] = (code >> 8) as u8;
            } else {
                payload[b] |= (code << 4) as u8;
                payload[b + 1] = (code >> 4) as u8;
            }
            if e == 15 {
                exception_positions.push(i);
                payload.extend_from_slice(&v.to_le_bytes());
                exceptions += 1;
            }
        }
        Self {
            payload,
            table,
            words: input.len(),
            exceptions,
            exception_offset,
            exception_positions,
        }
    }
    /// `payload` must be the exact admitted bytes, including vector-load padding.
    /// Output must contain `words` writable, non-overlapping u16 elements.
    /// SIMD selection and extent/integrity checks belong to admission, not here.
    pub unsafe fn decode(
        &self,
        payload: &[u8],
        output: &mut [u16],
        pool: &rayon::ThreadPool,
        simd: bool,
    ) {
        let chunk = self.words.div_ceil(4).next_multiple_of(8).max(8);
        pool.install(|| {
            output
                .par_chunks_mut(chunk)
                .enumerate()
                .for_each(|(part, out)| {
                    let start = part * chunk;
                    #[cfg(target_arch = "x86_64")]
                    if simd {
                        unsafe {
                            decode_simd(
                                payload.as_ptr().add(start * 3 / 2),
                                out.as_mut_ptr(),
                                out.len(),
                                self.table.as_ptr(),
                            )
                        };
                        return;
                    }
                    let _ = simd;
                    for (j, v) in out.iter_mut().enumerate() {
                        let i = start + j;
                        let b = i * 3 / 2;
                        let code = if i % 2 == 0 {
                            u16::from(payload[b]) | ((u16::from(payload[b + 1]) & 15) << 8)
                        } else {
                            (u16::from(payload[b]) >> 4) | (u16::from(payload[b + 1]) << 4)
                        };
                        *v = (code & 127)
                            | ((code & 128) << 8)
                            | (u16::from(self.table[(code >> 8) as usize]) << 7);
                    }
                })
        });
        // Positions are admitted RAM metadata, never unchecked indices read from disk.
        for (&index, row) in self
            .exception_positions
            .iter()
            .zip(payload[self.exception_offset..].chunks_exact(2))
        {
            unsafe {
                *output.get_unchecked_mut(index) = u16::from_le_bytes([row[0], row[1]]);
            }
        }
    }
}
#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "ssse3,sse4.1")]
unsafe fn decode_simd(source: *const u8, output: *mut u16, n: usize, table: *const u8) {
    use std::arch::x86_64::*;
    unsafe {
        let shuffle = _mm_setr_epi8(0, 1, 1, 2, 3, 4, 4, 5, 6, 7, 7, 8, 9, 10, 10, 11);
        let exp = _mm_loadu_si128(table.cast());
        let streaming = (output as usize) % 16 == 0;
        let mut i = 0;
        while i + 8 <= n {
            let raw = _mm_shuffle_epi8(_mm_loadu_si128(source.add(i * 3 / 2).cast()), shuffle);
            let code = _mm_blend_epi16(
                _mm_and_si128(raw, _mm_set1_epi16(4095)),
                _mm_srli_epi16(raw, 4),
                0xaa,
            );
            let exponent = _mm_and_si128(
                _mm_slli_epi16(_mm_shuffle_epi8(exp, _mm_srli_epi16(code, 8)), 7),
                _mm_set1_epi16(0x7f80),
            );
            let sign = _mm_slli_epi16(_mm_and_si128(code, _mm_set1_epi16(128)), 8);
            let value = _mm_or_si128(
                exponent,
                _mm_or_si128(sign, _mm_and_si128(code, _mm_set1_epi16(127))),
            );
            if streaming {
                _mm_stream_si128(output.add(i).cast(), value);
            } else {
                _mm_storeu_si128(output.add(i).cast(), value);
            }
            i += 8;
        }
        if streaming {
            _mm_sfence();
        }
        while i < n {
            let b = i * 3 / 2;
            let code = if i % 2 == 0 {
                u16::from(*source.add(b)) | ((u16::from(*source.add(b + 1)) & 15) << 8)
            } else {
                (u16::from(*source.add(b)) >> 4) | (u16::from(*source.add(b + 1)) << 4)
            };
            *output.add(i) = (code & 127)
                | ((code & 128) << 8)
                | (u16::from(*table.add((code >> 8) as usize)) << 7);
            i += 1;
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn every_bf16_bit_pattern_and_partial_vectors_roundtrip() {
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(4)
            .build()
            .unwrap();
        let all: Vec<u16> = (0..=u16::MAX).collect();
        for n in [1, 7, 8, 9, 31, 128, all.len()] {
            let e = Encoded::encode(&all[..n]);
            for simd in [false, true] {
                #[cfg(target_arch = "x86_64")]
                if simd
                    && !(is_x86_feature_detected!("ssse3") && is_x86_feature_detected!("sse4.1"))
                {
                    continue;
                }
                let mut out = vec![0; n];
                unsafe { e.decode(&e.payload, &mut out, &pool, simd) };
                assert_eq!(out, &all[..n]);
            }
        }
    }
}
