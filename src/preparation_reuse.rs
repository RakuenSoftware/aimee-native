//! Private computation reuse only. Aimee still authorizes each complete request.
//! Negative positions depend on total length; reuse requires an identical length.
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    ffi::{CStr, CString, c_char, c_void},
};
#[derive(Clone, Deserialize)]
struct Input {
    identity: BTreeMap<String, serde_json::Value>,
    tokens: Vec<u32>,
}
impl Input {
    fn scope(&self) -> Result<Vec<String>, ()> {
        [
            "recipient",
            "authorized_view",
            "model_revision",
            "runtime_profile",
            "encoding_revision",
            "position_policy",
        ]
        .iter()
        .map(|k| {
            self.identity
                .get(*k)
                .and_then(|v| v.as_str())
                .filter(|s| !s.is_empty())
                .map(str::to_owned)
                .ok_or(())
        })
        .collect()
    }
}
#[derive(Serialize)]
struct Plan {
    prefix: usize,
    tokens: usize,
    same_scope: bool,
}
struct Planner {
    previous: Option<Input>,
    limit: usize,
    response: CString,
}
impl Planner {
    fn plan(&self, input: &Input) -> Result<Plan, ()> {
        if input.tokens.is_empty() || input.tokens.len() > self.limit {
            return Err(());
        }
        let scope = input.scope()?;
        let same_scope = self
            .previous
            .as_ref()
            .is_some_and(|p| p.scope().ok().as_ref() == Some(&scope));
        let prefix = self
            .previous
            .as_ref()
            .filter(|p| same_scope && p.tokens.len() == input.tokens.len())
            .map(|p| {
                p.tokens
                    .iter()
                    .zip(&input.tokens)
                    .take_while(|(a, b)| a == b)
                    .count()
            })
            .unwrap_or(0);
        Ok(Plan {
            prefix,
            tokens: input.tokens.len(),
            same_scope,
        })
    }
}
#[unsafe(no_mangle)]
pub extern "C" fn aimee_reuse_open(limit: usize) -> *mut c_void {
    if limit == 0 || limit > 65536 {
        return std::ptr::null_mut();
    }
    Box::into_raw(Box::new(Planner {
        previous: None,
        limit,
        response: CString::default(),
    }))
    .cast()
}
/// Live exclusive handle and a NUL-terminated bounded JSON input. Commit only
/// after successful complete model evaluation. No candidate commits on a miss.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_reuse_plan(
    handle: *mut c_void,
    input: *const c_char,
    commit: bool,
) -> *const c_char {
    if handle.is_null() || input.is_null() {
        return std::ptr::null();
    }
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        let p = unsafe { &mut *handle.cast::<Planner>() };
        let raw = unsafe { CStr::from_ptr(input) }.to_bytes();
        if raw.len() > 8 * 1024 * 1024 {
            return std::ptr::null();
        }
        let Ok(input) = serde_json::from_slice::<Input>(raw) else {
            return std::ptr::null();
        };
        let Ok(plan) = p.plan(&input) else {
            return std::ptr::null();
        };
        p.response = CString::new(serde_json::to_vec(&plan).unwrap()).unwrap();
        if commit {
            p.previous = Some(input);
        }
        p.response.as_ptr()
    }))
    .unwrap_or(std::ptr::null())
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_reuse_close(handle: *mut c_void) {
    if !handle.is_null() {
        drop(unsafe { Box::from_raw(handle.cast::<Planner>()) });
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn input(tokens: &[u32]) -> Input {
        Input {
            identity: [
                "recipient",
                "authorized_view",
                "model_revision",
                "runtime_profile",
                "encoding_revision",
                "position_policy",
            ]
            .into_iter()
            .map(|s| (s.into(), serde_json::Value::String(s.into())))
            .collect(),
            tokens: tokens.into(),
        }
    }
    #[test]
    fn positions_scope_and_successful_commit_bound_reuse() {
        let mut p = Planner {
            previous: None,
            limit: 8,
            response: CString::default(),
        };
        assert_eq!(p.plan(&input(&[1, 2, 3])).unwrap().prefix, 0);
        p.previous = Some(input(&[1, 2, 3]));
        assert_eq!(p.plan(&input(&[1, 2, 4])).unwrap().prefix, 2);
        assert_eq!(p.plan(&input(&[1, 2, 3])).unwrap().prefix, 3);
        assert_eq!(p.plan(&input(&[1, 2, 3, 4])).unwrap().prefix, 0);
        assert_eq!(p.plan(&input(&[2, 1, 3])).unwrap().prefix, 0);
        for k in [
            "recipient",
            "authorized_view",
            "model_revision",
            "runtime_profile",
            "encoding_revision",
            "position_policy",
        ] {
            let mut i = input(&[1, 2, 3]);
            i.identity.insert(k.into(), "changed".into());
            assert_eq!(p.plan(&i).unwrap().prefix, 0);
        }
        let mut missing = input(&[1]);
        missing.identity.remove("recipient");
        assert!(p.plan(&missing).is_err());
        assert!(p.plan(&input(&[])).is_err());
        assert!(p.plan(&input(&[0; 9])).is_err());
        // Merely planning a different request must not replace the previous state.
        assert_eq!(p.plan(&input(&[1, 2, 3])).unwrap().prefix, 3);
    }
}
