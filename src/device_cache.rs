//! Device residency policy. No CUDA dependency, storage I/O, hashing or encoding.
//! The owner executes each accepted eviction/upload plan synchronously. A failed
//! upload poisons the owner; it must not execute attention using a partial plan.
use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Bank {
    pub id: u64,
    pub bytes: usize,
}
#[derive(Clone)]
struct Resident {
    bytes: usize,
    touched: u64,
}
#[derive(Clone)]
pub struct DeviceCache {
    budget: usize,
    epoch: u64,
    resident: BTreeMap<u64, Resident>,
}
#[derive(Debug, Serialize)]
pub struct Plan {
    pub evict: Vec<u64>,
    pub upload: Vec<u64>,
    pub resident_bytes: usize,
}
impl DeviceCache {
    pub fn new(budget: usize) -> Result<Self> {
        ensure!(budget > 0, "device budget must be positive");
        Ok(Self {
            budget,
            epoch: 0,
            resident: BTreeMap::new(),
        })
    }
    pub fn reconcile(&mut self, required: &[Bank]) -> Result<Plan> {
        let mut pins = BTreeSet::new();
        let mut required_bytes = 0usize;
        for bank in required {
            ensure!(
                bank.bytes > 0 && pins.insert(bank.id),
                "invalid bank reservation"
            );
            required_bytes = required_bytes
                .checked_add(bank.bytes)
                .ok_or_else(|| anyhow::anyhow!("reservation overflow"))?;
            if let Some(old) = self.resident.get(&bank.id) {
                ensure!(old.bytes == bank.bytes, "bank revision changed");
            }
        }
        ensure!(
            required_bytes <= self.budget,
            "pinned native banks exceed device budget"
        );
        // All validation before mutation: rejected reservations preserve residency.
        let mut next = self.clone();
        next.epoch = next
            .epoch
            .checked_add(1)
            .ok_or_else(|| anyhow::anyhow!("cache epoch exhausted"))?;
        let mut bytes: usize = next.resident.values().map(|r| r.bytes).sum();
        let needed: usize = required
            .iter()
            .filter(|b| !next.resident.contains_key(&b.id))
            .map(|b| b.bytes)
            .sum();
        let mut idle: Vec<_> = next
            .resident
            .iter()
            .filter(|(id, _)| !pins.contains(id))
            .map(|(id, r)| (r.touched, *id))
            .collect();
        idle.sort_unstable();
        let mut evict = Vec::new();
        for (_, id) in idle {
            if needed <= self.budget - bytes {
                break;
            }
            bytes -= next.resident.remove(&id).unwrap().bytes;
            evict.push(id);
        }
        let mut upload = Vec::new();
        for bank in required {
            if !next.resident.contains_key(&bank.id) {
                upload.push(bank.id);
                bytes += bank.bytes;
            }
            next.resident.insert(
                bank.id,
                Resident {
                    bytes: bank.bytes,
                    touched: next.epoch,
                },
            );
        }
        *self = next;
        Ok(Plan {
            evict,
            upload,
            resident_bytes: bytes,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn b(id: u64, bytes: usize) -> Bank {
        Bank { id, bytes }
    }
    #[test]
    fn idle_lru_eviction_preserves_active_pins() {
        let mut c = DeviceCache::new(20).unwrap();
        c.reconcile(&[b(1, 10), b(2, 10)]).unwrap();
        c.reconcile(&[b(2, 10)]).unwrap();
        let p = c.reconcile(&[b(2, 10), b(3, 10)]).unwrap();
        assert_eq!(p.evict, vec![1]);
        assert_eq!(p.upload, vec![3]);
        assert_eq!(p.resident_bytes, 20);
    }
    #[test]
    fn rejected_pressure_does_not_change_residency() {
        let mut c = DeviceCache::new(10).unwrap();
        c.reconcile(&[b(1, 10)]).unwrap();
        assert!(c.reconcile(&[b(1, 10), b(2, 1)]).is_err());
        let p = c.reconcile(&[b(1, 10)]).unwrap();
        assert!(p.upload.is_empty());
        assert!(p.evict.is_empty());
    }
    #[test]
    fn reloading_evicted_bank_requires_upload() {
        let mut c = DeviceCache::new(10).unwrap();
        c.reconcile(&[b(1, 10)]).unwrap();
        c.reconcile(&[b(2, 10)]).unwrap();
        let p = c.reconcile(&[b(1, 10)]).unwrap();
        assert_eq!(p.upload, vec![1]);
        assert_eq!(p.evict, vec![2]);
    }
    #[test]
    fn duplicate_revision_change_and_overflow_rejected() {
        let mut c = DeviceCache::new(usize::MAX).unwrap();
        c.reconcile(&[b(1, 10)]).unwrap();
        assert!(c.reconcile(&[b(1, 11)]).is_err());
        assert!(c.reconcile(&[b(2, 1), b(2, 1)]).is_err());
        assert!(c.reconcile(&[b(2, usize::MAX), b(3, 1)]).is_err());
        assert!(c.reconcile(&[b(1, 10)]).unwrap().upload.is_empty());
    }
}
