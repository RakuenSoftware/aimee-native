//! Archived lossless dictionary codec, retained to read the measured candidate.
//! New publications use transfer-ready layouts instead: application latency,
//! not compression ratio, is the objective. `pack` supports codec regression tests.
use anyhow::{Result, ensure};
pub const BLOCK: usize = 16384;
pub fn pack(input: &[u16]) -> Vec<u8> {
    let mut out = Vec::new();
    let mut indices = vec![u16::MAX; 65536];
    for block in input.chunks(BLOCK) {
        let mut palette = Vec::new();
        for &value in block {
            if indices[value as usize] == u16::MAX {
                indices[value as usize] = palette.len() as u16;
                palette.push(value);
            }
        }
        let width = if palette.len() <= 256 { 1 } else { 2 };
        let coded = if width == 1 {
            block.len()
        } else {
            block.len().div_ceil(2) * 3
        };
        if palette.len() > 4096 || 3 + palette.len() * 2 + coded >= 1 + block.len() * 2 {
            out.push(0);
            for &v in block {
                out.extend_from_slice(&v.to_le_bytes());
            }
        } else {
            out.push(width);
            out.extend_from_slice(&(palette.len() as u16).to_le_bytes());
            for &v in &palette {
                out.extend_from_slice(&v.to_le_bytes());
            }
            if width == 1 {
                for &v in block {
                    out.push(indices[v as usize] as u8);
                }
            } else {
                for pair in block.chunks(2) {
                    let a = indices[pair[0] as usize] as u32;
                    let b = pair.get(1).map_or(0, |&v| indices[v as usize] as u32);
                    out.extend_from_slice(&(a | b << 12).to_le_bytes()[..3]);
                }
            }
        }
        for v in palette {
            indices[v as usize] = u16::MAX;
        }
    }
    out
}
pub fn unpack(mut input: &[u8], output: &mut [u16]) -> Result<()> {
    let mut palette = [0u16; 4096];
    for block in output.chunks_mut(BLOCK) {
        ensure!(!input.is_empty(), "truncated intermediate header");
        let tag = input[0];
        input = &input[1..];
        if tag == 0 {
            ensure!(
                input.len() >= block.len() * 2,
                "truncated intermediate raw block"
            );
            for (dst, src) in block.iter_mut().zip(input.chunks_exact(2)) {
                *dst = u16::from_le_bytes([src[0], src[1]]);
            }
            input = &input[block.len() * 2..];
            continue;
        }
        ensure!(
            (tag == 1 || tag == 2) && input.len() >= 2,
            "invalid intermediate block"
        );
        let count = u16::from_le_bytes([input[0], input[1]]) as usize;
        input = &input[2..];
        ensure!(
            count > 0 && count <= if tag == 1 { 256 } else { 4096 },
            "invalid intermediate dictionary"
        );
        ensure!(
            input.len() >= count * 2,
            "truncated intermediate dictionary"
        );
        for (dst, src) in palette[..count].iter_mut().zip(input.chunks_exact(2)) {
            *dst = u16::from_le_bytes([src[0], src[1]]);
        }
        input = &input[count * 2..];
        if tag == 1 {
            ensure!(input.len() >= block.len(), "truncated intermediate indices");
            for (dst, &index) in block.iter_mut().zip(input.iter()) {
                ensure!((index as usize) < count, "invalid intermediate index");
                *dst = palette[index as usize];
            }
            input = &input[block.len()..];
        } else {
            let bytes = block.len().div_ceil(2) * 3;
            ensure!(input.len() >= bytes, "truncated intermediate indices");
            for (dst, src) in block.chunks_mut(2).zip(input[..bytes].chunks_exact(3)) {
                let a = src[0] as usize | ((src[1] as usize & 15) << 8);
                let b = (src[1] as usize >> 4) | ((src[2] as usize) << 4);
                ensure!(a < count && b < count, "invalid intermediate index");
                dst[0] = palette[a];
                if dst.len() == 2 {
                    dst[1] = palette[b];
                }
            }
            input = &input[bytes..];
        }
    }
    ensure!(input.is_empty(), "trailing intermediate bytes");
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_all_bits_and_all_blocks() {
        for size in [0, 1, 255, 16384, 16385, 65536] {
            for cardinality in [1, 128, 2048, 65536] {
                let input: Vec<_> = (0..size)
                    .map(|i| ((i * 7919) % cardinality) as u16)
                    .collect();
                let bytes = pack(&input);
                let mut output = vec![0; size];
                unpack(&bytes, &mut output).unwrap();
                assert_eq!(input, output);
                if size > 1000 && cardinality <= 2048 {
                    assert!(bytes.len() < input.len() * 2);
                }
            }
        }
    }
    #[test]
    fn malformed_payloads_are_rejected() {
        let input = vec![123; 512];
        let bytes = pack(&input);
        for len in 0..bytes.len() {
            assert!(unpack(&bytes[..len], &mut vec![0; 512]).is_err());
        }
        let mut invalid = bytes.clone();
        *invalid.last_mut().unwrap() = 255;
        assert!(unpack(&invalid, &mut vec![0; 512]).is_err());
        let mut extra = bytes;
        extra.push(0);
        assert!(unpack(&extra, &mut vec![0; 512]).is_err());
    }
}
