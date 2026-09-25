//! Lossless record codecs. Compression is offline; decode writes into the active
//! tensor buffer. Byte-plane mode leaves low bytes literal and compresses only
//! the more repetitive high bytes of 16-bit values. No numerical quantization.
use anyhow::{Result, ensure};
#[derive(
    Clone, Copy, Default, serde::Serialize, serde::Deserialize, clap::ValueEnum, PartialEq,
)]
#[serde(rename_all = "kebab-case")]
pub enum Codec {
    #[default]
    Raw,
    Lz4,
    Lz4Byteplane,
    Lz4ByteplaneParallel,
    Lz4ByteplaneHc,
    Lz4ByteplaneHcParallel,
}
const CHUNK: usize = 64 * 1024;
fn pool() -> &'static rayon::ThreadPool {
    static POOL: std::sync::OnceLock<rayon::ThreadPool> = std::sync::OnceLock::new();
    POOL.get_or_init(|| {
        rayon::ThreadPoolBuilder::new()
            .num_threads(8)
            .thread_name(|i| format!("native-decode-{i}"))
            .build()
            .expect("native decode pool")
    })
}
pub fn initialize() {
    let _ = pool();
}
pub fn encode(codec: Codec, data: &[u8]) -> Result<Vec<u8>> {
    Ok(match codec {
        Codec::Lz4ByteplaneParallel | Codec::Lz4ByteplaneHcParallel => {
            let blocks: Vec<_> = data
                .chunks(CHUNK)
                .map(|b| {
                    encode(
                        if codec == Codec::Lz4ByteplaneHcParallel {
                            Codec::Lz4ByteplaneHc
                        } else {
                            Codec::Lz4Byteplane
                        },
                        b,
                    )
                })
                .collect::<Result<_>>()?;
            let mut out = Vec::new();
            for b in &blocks {
                out.extend_from_slice(&(b.len() as u32).to_le_bytes());
            }
            for b in blocks {
                out.extend_from_slice(&b);
            }
            out
        }
        Codec::Raw => data.to_vec(),
        Codec::Lz4 => lz4_flex::block::compress(data),
        Codec::Lz4Byteplane | Codec::Lz4ByteplaneHc => {
            ensure!(
                data.len() % 2 == 0,
                "byte-plane codec requires 16-bit extent"
            );
            let mut low = Vec::with_capacity(data.len());
            let mut high = Vec::with_capacity(data.len() / 2);
            for pair in data.chunks_exact(2) {
                low.push(pair[0]);
                high.push(pair[1]);
            }
            let packed = if codec == Codec::Lz4ByteplaneHc {
                lz4::block::compress(
                    &high,
                    Some(lz4::block::CompressionMode::HIGHCOMPRESSION(12)),
                    false,
                )?
            } else {
                lz4_flex::block::compress(&high)
            };
            low.extend_from_slice(&packed);
            low
        }
    })
}
pub fn decode(codec: Codec, input: &[u8], output: &mut [u8], scratch: &mut Vec<u8>) -> Result<()> {
    match codec {
        Codec::Lz4ByteplaneParallel | Codec::Lz4ByteplaneHcParallel => {
            use rayon::prelude::*;
            let count = output.len().div_ceil(CHUNK);
            let header = count * 4;
            ensure!(input.len() >= header, "truncated chunk table");
            let mut blocks = Vec::with_capacity(count);
            let mut offset = header;
            for size in input[..header].chunks_exact(4) {
                let n = u32::from_le_bytes(size.try_into().unwrap()) as usize;
                let end = offset
                    .checked_add(n)
                    .ok_or_else(|| anyhow::anyhow!("chunk overflow"))?;
                blocks.push(
                    input
                        .get(offset..end)
                        .ok_or_else(|| anyhow::anyhow!("truncated chunk"))?,
                );
                offset = end;
            }
            ensure!(offset == input.len(), "chunk extent mismatch");
            pool().install(||output.par_chunks_mut(CHUNK).zip(blocks.par_iter()).try_for_each(|(dst,src)|{
                thread_local!{static SCRATCH:std::cell::RefCell<Vec<u8>>=const{std::cell::RefCell::new(Vec::new())};}
                SCRATCH.with(|s|decode(if codec==Codec::Lz4ByteplaneHcParallel {Codec::Lz4ByteplaneHc}else{Codec::Lz4Byteplane},src,dst,&mut s.borrow_mut()))
            }))?;
        }
        Codec::Raw => {
            ensure!(input.len() == output.len(), "raw extent mismatch");
            output.copy_from_slice(input);
        }
        Codec::Lz4 => {
            let n = lz4_flex::block::decompress_into(input, output)?;
            ensure!(n == output.len(), "decoded extent mismatch");
        }
        Codec::Lz4Byteplane | Codec::Lz4ByteplaneHc => {
            let n = output.len() / 2;
            ensure!(
                output.len() % 2 == 0 && input.len() >= n,
                "invalid byte-plane extent"
            );
            scratch.resize(n, 0);
            let decoded = if codec == Codec::Lz4ByteplaneHc {
                lz4::block::decompress_to_buffer(&input[n..], Some(n.try_into()?), scratch)?
            } else {
                lz4_flex::block::decompress_into(&input[n..], scratch)?
            };
            ensure!(decoded == n, "decoded plane extent mismatch");
            for ((dst, &lo), &hi) in output
                .chunks_exact_mut(2)
                .zip(&input[..n])
                .zip(scratch.iter())
            {
                dst[0] = lo;
                dst[1] = hi;
            }
        }
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn every_bit_is_preserved_including_float_special_values() {
        let bytes: Vec<u8> = (0u32..65536)
            .flat_map(|v| (v as u16).to_le_bytes())
            .collect();
        for codec in [
            Codec::Raw,
            Codec::Lz4,
            Codec::Lz4Byteplane,
            Codec::Lz4ByteplaneParallel,
            Codec::Lz4ByteplaneHc,
            Codec::Lz4ByteplaneHcParallel,
        ] {
            let packed = encode(codec, &bytes).unwrap();
            let mut result = vec![0; bytes.len()];
            decode(codec, &packed, &mut result, &mut Vec::new()).unwrap();
            assert_eq!(result, bytes);
        }
    }
}
