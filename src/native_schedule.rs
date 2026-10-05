//! Deterministic research scheduling. Never substitutes for generation checks.
use anyhow::{Result, ensure};
use serde_json::{Value, json};

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, clap::ValueEnum)]
pub enum Mode {
    #[default]
    EveryStep,
    PreloadOnly,
    BoundedRefresh,
}

#[derive(Clone, Copy, Debug)]
pub struct Policy {
    pub mode: Mode,
    pub interval: usize,
    pub max_reads: usize,
}
impl Default for Policy {
    fn default() -> Self {
        Self {
            mode: Mode::EveryStep,
            interval: 1,
            max_reads: usize::MAX,
        }
    }
}
impl Policy {
    pub fn validate(self) -> Result<Self> {
        ensure!(self.interval > 0, "refresh interval must be positive");
        ensure!(self.max_reads > 0, "read budget must be positive");
        ensure!(
            self.mode != Mode::BoundedRefresh || self.max_reads != usize::MAX,
            "bounded refresh requires a finite read budget"
        );
        Ok(self)
    }
    pub fn due(self, step: usize, decode_enabled: bool, reads: usize) -> bool {
        if reads >= self.max_reads || self.mode == Mode::PreloadOnly {
            return false;
        }
        (step == 0 || decode_enabled) && (self.mode == Mode::EveryStep || step % self.interval == 0)
    }
    pub fn describe(self) -> Value {
        json!({"mode":match self.mode { Mode::EveryStep=>"every-step",
            Mode::PreloadOnly=>"preload-only", Mode::BoundedRefresh=>"bounded-refresh" },
            "interval_steps":self.interval,
            "max_source_reads":if self.max_reads == usize::MAX {None} else {Some(self.max_reads)}})
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn legacy_and_preload_have_exact_cadence() {
        let legacy = Policy::default();
        assert!(legacy.due(0, false, 0));
        assert!(!legacy.due(1, false, 0));
        assert!(legacy.due(100, true, 200));
        let preload = Policy {
            mode: Mode::PreloadOnly,
            ..legacy
        };
        assert!(!(0..100).any(|s| preload.due(s, true, 0)));
    }
    #[test]
    fn bounded_policy_counts_preload_and_failed_calls() {
        let p = Policy {
            mode: Mode::BoundedRefresh,
            interval: 4,
            max_reads: 3,
        };
        assert_eq!(
            (0..10).filter(|s| p.due(*s, true, 1)).collect::<Vec<_>>(),
            vec![0, 4, 8]
        );
        assert!(!p.due(8, true, 3));
        assert!(!p.due(4, false, 1));
        assert!(Policy { interval: 0, ..p }.validate().is_err());
        assert!(Policy { max_reads: 0, ..p }.validate().is_err());
        assert!(
            Policy {
                max_reads: usize::MAX,
                ..p
            }
            .validate()
            .is_err()
        );
    }
}
