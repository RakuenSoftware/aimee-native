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
    #[serde(default)]
    pub staging_bytes: usize,
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
    pub peak_bytes: usize,
    pub staging_limits: BTreeMap<u64, usize>,
    pub raw_upload: Vec<u64>,
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
        let mut staging_limits = BTreeMap::new();
        let mut raw_upload = Vec::new();
        let mut peak_bytes = bytes;
        // Large transient allocations first minimize the maximum sequential peak.
        // Staging is released after each synchronous upload; only dense bytes stay.
        let mut pending: Vec<_> = required.iter()
            .filter(|b| !next.resident.contains_key(&b.id)).collect();
        pending.sort_by_key(|b| (std::cmp::Reverse(b.staging_bytes), b.id));
        for bank in pending {
            upload.push(bank.id);
            bytes += bank.bytes;
            let available = self.budget - bytes;
            staging_limits.insert(bank.id, available);
            let staging = if bank.staging_bytes <= available { bank.staging_bytes } else {
                raw_upload.push(bank.id);
                0
            };
            peak_bytes = peak_bytes.max(bytes + staging);
        }
        for bank in required {
            next.resident.insert(bank.id, Resident { bytes: bank.bytes, touched: next.epoch });
        }
        *self = next;
        Ok(Plan {
            evict,
            upload,
            resident_bytes: bytes,
            peak_bytes,
            staging_limits,
            raw_upload,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn b(id: u64, bytes: usize) -> Bank {
        Bank { id, bytes, staging_bytes: 0 }
    }
    #[test]
    fn transient_staging_is_released_between_uploads_and_residency() {
        let mut c=DeviceCache::new(30).unwrap();
        let banks: Vec<_>=(1..=3).map(|id| Bank{id,bytes:10,staging_bytes:8}).collect();
        let p=c.reconcile(&banks).unwrap();
        assert_eq!(p.resident_bytes,30);
        assert_eq!(p.peak_bytes,30);
        assert_eq!(p.raw_upload,vec![3]);
        let p=c.reconcile(&banks).unwrap();
        assert!(p.upload.is_empty());
        assert!(p.evict.is_empty());
        assert_eq!(p.peak_bytes,30);
    }
    #[test]
    fn staging_pressure_does_not_evict_an_otherwise_fitting_idle_bank() {
        let mut c=DeviceCache::new(20).unwrap();
        c.reconcile(&[b(1,10)]).unwrap();
        let p=c.reconcile(&[Bank{id:2,bytes:10,staging_bytes:8}]).unwrap();
        assert!(p.evict.is_empty());
        assert_eq!(p.raw_upload,vec![2]);
        assert_eq!(p.resident_bytes,20);
        assert_eq!(p.peak_bytes,20);
    }
    #[test]
    fn upload_order_places_large_staging_first() {
        let mut c=DeviceCache::new(30).unwrap();
        let p=c.reconcile(&[Bank{id:1,bytes:10,staging_bytes:1},Bank{id:2,bytes:10,staging_bytes:19}]).unwrap();
        assert_eq!(p.upload,vec![2,1]);
        assert!(p.raw_upload.is_empty());
        assert_eq!(p.peak_bytes,29);
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

/// Frontend reservations count unique active banks, matching worker residency.
/// No memory payload or GPU operation belongs in this ledger.
pub struct Admission {
    budget: usize,
    used: usize,
    active: BTreeMap<u64, (usize, usize)>,
}
impl Admission {
    pub fn new(budget: usize) -> Self {
        Self {
            budget,
            used: 0,
            active: BTreeMap::new(),
        }
    }
    pub fn acquire(&mut self, id: u64, bytes: usize) -> bool {
        if bytes == 0 {
            return false;
        }
        if let Some((size, refs)) = self.active.get_mut(&id) {
            if *size != bytes || *refs == usize::MAX {
                return false;
            }
            *refs += 1;
            return true;
        }
        if bytes > self.budget - self.used {
            return false;
        }
        self.active.insert(id, (bytes, 1));
        self.used += bytes;
        true
    }
    pub fn release(&mut self, id: u64) {
        if let Some((bytes, refs)) = self.active.get_mut(&id) {
            *refs -= 1;
            if *refs == 0 {
                self.used -= *bytes;
                self.active.remove(&id);
            }
        }
    }
}
#[cfg(test)]
mod admission_tests {
    use super::*;
    #[test]
    fn shared_bank_counts_once_but_releases_after_last_request() {
        let mut a = Admission::new(10);
        assert!(a.acquire(1, 10));
        assert!(a.acquire(1, 10));
        assert!(!a.acquire(2, 1));
        a.release(1);
        assert!(!a.acquire(2, 1));
        a.release(1);
        assert!(a.acquire(2, 10));
    }
    #[test]
    fn different_revisions_compete_and_rejection_preserves_reservations() {
        let mut a = Admission::new(20);
        assert!(a.acquire(1, 10));
        assert!(a.acquire(2, 10));
        assert!(!a.acquire(3, 1));
        assert!(!a.acquire(1, 11));
        a.release(2);
        assert!(a.acquire(3, 10));
    }
}
