//! Retained owned backing files with active/idle lifecycle; no integrity checks.
use anyhow::{Result, ensure};
use std::{
    collections::HashMap,
    fs::File,
    path::{Path, PathBuf},
    sync::{Arc, Mutex, mpsc},
    thread,
    time::{Duration, Instant},
};
struct Active {
    file: Arc<File>,
    used: Instant,
}
pub struct Files {
    active: Arc<Mutex<HashMap<PathBuf, Active>>>,
    stop: mpsc::Sender<()>,
    worker: Option<thread::JoinHandle<()>>,
}
impl Files {
    pub fn new(idle: Duration) -> Result<Self> {
        ensure!(!idle.is_zero(), "prepared idle timeout must be positive");
        let active = Arc::new(Mutex::new(HashMap::<PathBuf, Active>::new()));
        let shared = active.clone();
        let (stop, rx) = mpsc::channel();
        let worker = thread::Builder::new()
            .name("prepared-file-idle".into())
            .spawn(move || {
                while matches!(
                    rx.recv_timeout(idle.min(Duration::from_secs(1))),
                    Err(mpsc::RecvTimeoutError::Timeout)
                ) {
                    let now = Instant::now();
                    shared.lock().unwrap().retain(|_, v| {
                        if Arc::strong_count(&v.file) > 1 {
                            v.used = now;
                            true
                        } else {
                            now.duration_since(v.used) < idle
                        }
                    });
                }
            })?;
        Ok(Self {
            active,
            stop,
            worker: Some(worker),
        })
    }
    /// Reuse owned backing files; no content, extent or hash verification here.
    pub fn acquire(&self, path: &Path) -> Result<(Arc<File>, bool)> {
        let mut active = self.active.lock().unwrap();
        if let Some(v) = active.get_mut(path) {
            v.used = Instant::now();
            return Ok((v.file.clone(), false));
        }
        let file = Arc::new(File::open(path)?);
        active.insert(
            path.into(),
            Active {
                file: file.clone(),
                used: Instant::now(),
            },
        );
        Ok((file, true))
    }
    pub fn clear(&self) {
        self.active.lock().unwrap().clear();
    }
}
impl Drop for Files {
    fn drop(&mut self) {
        let _ = self.stop.send(());
        if let Some(w) = self.worker.take() {
            let _ = w.join();
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::FileExt;
    #[test]
    fn one_file_multiple_ranges_retained_then_closed_after_idle() {
        let dir = tempfile::tempdir().unwrap();
        let p = dir.path().join("pack");
        std::fs::write(&p, b"abcdEFGH").unwrap();
        let c = Files::new(Duration::from_millis(20)).unwrap();
        let (a, first) = c.acquire(&p).unwrap();
        assert!(first);
        let (b, second) = c.acquire(&p).unwrap();
        assert!(!second);
        assert!(Arc::ptr_eq(&a, &b));
        std::fs::rename(&p, dir.path().join("old")).unwrap();
        std::fs::write(&p, b"xxxxxxxx").unwrap();
        thread::sleep(Duration::from_millis(60));
        assert!(!c.acquire(&p).unwrap().1);
        let mut out = [0; 4];
        b.read_exact_at(&mut out, 4).unwrap();
        assert_eq!(&out, b"EFGH");
        drop(a);
        drop(b);
        let deadline = Instant::now() + Duration::from_secs(2);
        while !c.active.lock().unwrap().is_empty() && Instant::now() < deadline {
            thread::sleep(Duration::from_millis(10));
        }
        assert!(c.active.lock().unwrap().is_empty());
        assert!(c.acquire(&p).unwrap().1);
    }
    #[test]
    fn append_admission_and_short_read_failure() {
        use std::io::Write;
        let dir = tempfile::tempdir().unwrap();
        let p = dir.path().join("pack");
        std::fs::write(&p, b"abcd").unwrap();
        let c = Files::new(Duration::from_secs(60)).unwrap();
        let (a, _) = c.acquire(&p).unwrap();
        std::fs::OpenOptions::new()
            .append(true)
            .open(&p)
            .unwrap()
            .write_all(b"abcd")
            .unwrap();
        let (b, new) = c.acquire(&p).unwrap();
        assert!(!new);
        assert!(Arc::ptr_eq(&a, &b));
        std::fs::OpenOptions::new()
            .write(true)
            .open(&p)
            .unwrap()
            .set_len(2)
            .unwrap();
        assert!(a.read_exact_at(&mut [0; 4], 0).is_err());
    }
}
