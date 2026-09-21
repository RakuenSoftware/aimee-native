package sparse

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"syscall"
)

const deliveryFormat = "aimee-recipient-delivery-v1\n"

// Delivery is owned by the publisher, not the model. It accepts only snapshots
// already filtered for this recipient. No authorization decision occurs here.
type Delivery struct{ Root string }

type DeliveryResult struct {
	View             string `json:"view"`
	Previous         string `json:"previous"`
	ReusedBytes      int64  `json:"reused_bytes"`
	CopiedBytes      int64  `json:"copied_bytes"`
	RemovedSnapshots int    `json:"removed_snapshots"`
}

func (d Delivery) initialize(gid int) error {
	err := os.Mkdir(d.Root, 0750)
	if os.IsExist(err) {
		info, e := os.Lstat(d.Root)
		if e != nil {
			return e
		}
		if !info.IsDir() {
			return fmt.Errorf("delivery root must be a directory")
		}
		b, e := os.ReadFile(filepath.Join(d.Root, "DELIVERY"))
		if e != nil || string(b) != deliveryFormat {
			return fmt.Errorf("refusing unmanaged delivery directory")
		}
		if gid >= 0 && int(info.Sys().(*syscall.Stat_t).Gid) != gid {
			return fmt.Errorf("existing delivery group differs")
		}
		return nil
	}
	if err != nil {
		return err
	}
	if gid < 0 {
		gid = os.Getgid()
	}
	if err = os.Chmod(d.Root, 0750); err != nil {
		return err
	}
	if err = os.Chown(d.Root, -1, gid); err != nil {
		return err
	}
	if err = os.WriteFile(filepath.Join(d.Root, "DELIVERY"), []byte(deliveryFormat), 0640); err != nil {
		return err
	}
	if err = os.Mkdir(filepath.Join(d.Root, "snapshots"), 0750); err != nil {
		return err
	}
	if err = os.WriteFile(filepath.Join(d.Root, ".delivery.lock"), nil, 0640); err != nil {
		return err
	}
	for _, name := range []string{"DELIVERY", "snapshots", ".delivery.lock"} {
		mode := os.FileMode(0640)
		if name == "snapshots" {
			mode = 0750
		}
		if err = os.Chmod(filepath.Join(d.Root, name), mode); err != nil {
			return err
		}
		if err = os.Chown(filepath.Join(d.Root, name), -1, gid); err != nil {
			return err
		}
	}
	return syncDir(d.Root)
}

func (d Delivery) lock(exclusive bool) (*os.File, error) {
	b, err := os.ReadFile(filepath.Join(d.Root, "DELIVERY"))
	if err != nil {
		return nil, err
	}
	if string(b) != deliveryFormat {
		return nil, fmt.Errorf("unsupported delivery format")
	}
	// Serialize entry to the read/write lock. Without this turnstile, a
	// continuous stream of new shared opens can starve a waiting publisher.
	// Hold it only until the main lock is acquired, never through steady reads.
	gatePath := filepath.Join(d.Root, ".delivery.gate")
	if exclusive {
		info, e := os.Stat(d.Root)
		if e != nil {
			return nil, e
		}
		gate, e := os.OpenFile(gatePath, os.O_CREATE|os.O_RDWR, 0640)
		if e != nil {
			return nil, e
		}
		e = gate.Chown(-1, int(info.Sys().(*syscall.Stat_t).Gid))
		gate.Close()
		if e != nil {
			return nil, e
		}
	}
	gate, e := os.Open(gatePath)
	if e == nil {
		defer gate.Close()
		if e = syscall.Flock(int(gate.Fd()), syscall.LOCK_EX); e != nil {
			return nil, e
		}
	} else if !os.IsNotExist(e) {
		return nil, e
	}
	f, err := os.Open(filepath.Join(d.Root, ".delivery.lock"))
	if err != nil {
		return nil, err
	}
	mode := syscall.LOCK_SH
	if exclusive {
		mode = syscall.LOCK_EX
	}
	if err = syscall.Flock(int(f.Fd()), mode); err != nil {
		f.Close()
		return nil, err
	}
	return f, nil // closing releases flock
}

func (d Delivery) current() (string, error) {
	id, err := (Store{d.Root}).Current()
	if os.IsNotExist(err) {
		return "", nil
	}
	return id, err
}

// Install copies the reachable objects only, verifies the completed staging
// snapshot, switches CURRENT atomically, then unlinks obsolete directories.
// A short shared reader lock covers pin/open only; active reads use open files.
func (d Delivery) Install(src Store, expected string, gid int) (DeliveryResult, error) {
	return d.install(src, expected, gid, nil)
}
func (d Delivery) install(src Store, expected string, gid int, beforeCommit func() error) (out DeliveryResult, err error) {
	id, err := src.Current()
	if err != nil {
		return out, err
	}
	p, err := src.OpenPublished(id)
	if err != nil {
		return out, err
	}
	defer p.Close()
	if err = d.initialize(gid); err != nil {
		return out, err
	}
	lock, err := d.lock(true)
	if err != nil {
		return out, err
	}
	defer lock.Close()
	out.Previous, err = d.current()
	if err != nil {
		return out, err
	}
	if out.Previous != expected {
		return out, fmt.Errorf("delivery conflict: current generation changed")
	}
	out.View = id
	if id == out.Previous {
		out.RemovedSnapshots, err = d.prune(id)
		return out, err
	}
	info, err := os.Stat(d.Root)
	if err != nil {
		return out, err
	}
	gid = int(info.Sys().(*syscall.Stat_t).Gid)
	stage, err := os.MkdirTemp(filepath.Join(d.Root, "snapshots"), ".stage-")
	if err != nil {
		return out, err
	}
	defer os.RemoveAll(stage)
	if err = os.Mkdir(filepath.Join(stage, "objects"), 0700); err != nil {
		return out, err
	}
	objects := map[string]bool{}
	for head := id; head != ""; {
		m, e := src.manifest(head)
		if e != nil {
			return out, e
		}
		objects[head] = true
		objects[m.Data] = true
		objects[m.Index] = true
		head = m.Upstream
	}
	names := make([]string, 0, len(objects))
	for h := range objects {
		names = append(names, h)
	}
	sort.Strings(names)
	for _, h := range names {
		path, _ := src.object(h)
		dest := filepath.Join(stage, "objects", h)
		if out.Previous != "" {
			old := filepath.Join(d.Root, "snapshots", out.Previous, "objects", h)
			if info, e := os.Stat(old); e == nil && info.Mode().IsRegular() {
				if e = os.Link(old, dest); e == nil {
					out.ReusedBytes += info.Size()
					continue
				}
			}
		}
		n, e := copyDeliveryObject(path, dest, h)
		if e != nil {
			return out, e
		}
		out.CopiedBytes += n
	}
	if err = writeDeliveryHead(stage, id); err != nil {
		return out, err
	}
	check, err := (Store{stage}).OpenPublished(id)
	if err != nil {
		return out, err
	}
	check.Close()
	if err = filepath.WalkDir(stage, func(path string, entry os.DirEntry, e error) error {
		if e != nil {
			return e
		}
		info, e := entry.Info()
		if e != nil {
			return e
		}
		if int(info.Sys().(*syscall.Stat_t).Gid) != gid {
			if e = os.Chown(path, -1, gid); e != nil {
				return e
			}
		}
		mode := os.FileMode(0640)
		if entry.IsDir() {
			mode = 0750
		}
		// Keep the staging root private through the final approval check.
		// Readable child modes do not release bytes while this root is 0700.
		if path == stage {
			mode = 0700
		}
		if info.Mode().Perm() == mode {
			return nil
		}
		return os.Chmod(path, mode)
	}); err != nil {
		return out, err
	}
	if err = syncDir(filepath.Join(stage, "objects")); err != nil {
		return out, err
	}
	if err = syncDir(stage); err != nil {
		return out, err
	}
	if beforeCommit != nil {
		if err = beforeCommit(); err != nil {
			return out, err
		}
	}
	target := filepath.Join(d.Root, "snapshots", id)
	// A prior interrupted install may have left this unpublished generation.
	if err = os.RemoveAll(target); err != nil {
		return out, err
	}
	if err = os.Rename(stage, target); err != nil {
		return out, err
	}
	if err = os.Chmod(target, 0750); err != nil {
		return out, err
	}
	if err = syncDir(filepath.Join(d.Root, "snapshots")); err != nil {
		return out, err
	}
	if err = writeDeliveryHead(d.Root, id); err != nil {
		return out, err
	}
	out.RemovedSnapshots, err = d.prune(id)
	if err != nil {
		err = fmt.Errorf("generation %s installed; cleanup incomplete: %w", id, err)
	}
	return out, err
}

func copyDeliveryObject(source, dest, hash string) (int64, error) {
	in, err := os.Open(source)
	if err != nil {
		return 0, err
	}
	defer in.Close()
	out, err := os.OpenFile(dest, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return 0, err
	}
	defer out.Close()
	h := sha256.New()
	n, err := io.Copy(io.MultiWriter(out, h), in)
	if err != nil {
		return n, err
	}
	if hex.EncodeToString(h.Sum(nil)) != hash {
		return n, fmt.Errorf("source changed during delivery")
	}
	if err = out.Sync(); err != nil {
		return n, err
	}
	return n, out.Close()
}

func writeDeliveryHead(root, id string) error {
	f, err := os.CreateTemp(root, ".head-")
	if err != nil {
		return err
	}
	defer os.Remove(f.Name())
	defer f.Close()
	info, err := os.Stat(root)
	if err != nil {
		return err
	}
	if err = f.Chown(-1, int(info.Sys().(*syscall.Stat_t).Gid)); err != nil {
		return err
	}
	if err = f.Chmod(0640); err != nil {
		return err
	}
	b, _ := json.Marshal(map[string]string{"view": id})
	if _, err = f.Write(b); err != nil {
		return err
	}
	if err = f.Sync(); err != nil {
		return err
	}
	if err = f.Close(); err != nil {
		return err
	}
	if err = os.Rename(f.Name(), filepath.Join(root, "CURRENT")); err != nil {
		return err
	}
	return syncDir(root)
}

// Prune is also the recovery operation after an interrupted publication. It
// never deletes the active generation and never traverses symlink targets.
func (d Delivery) Prune(expected string) (int, error) {
	lock, err := d.lock(true)
	if err != nil {
		return 0, err
	}
	defer lock.Close()
	id, err := d.current()
	if err != nil {
		return 0, err
	}
	if id != expected {
		return 0, fmt.Errorf("delivery conflict")
	}
	return d.prune(id)
}

func (d Delivery) prune(keep string) (int, error) {
	root := filepath.Join(d.Root, "snapshots")
	entries, err := os.ReadDir(root)
	if err != nil {
		return 0, err
	}
	n := 0
	for _, entry := range entries {
		name := entry.Name()
		if name == keep {
			continue
		}
		if !digestPattern.MatchString(name) && !strings.HasPrefix(name, ".stage-") {
			return n, fmt.Errorf("unexpected delivery entry %q", name)
		}
		if err = os.RemoveAll(filepath.Join(root, name)); err != nil {
			return n, err
		}
		n++
	}
	return n, syncDir(root)
}

func (d Delivery) Withdraw(expected string) (DeliveryResult, error) {
	out := DeliveryResult{}
	lock, err := d.lock(true)
	if err != nil {
		return out, err
	}
	defer lock.Close()
	out.Previous, err = d.current()
	if err != nil {
		return out, err
	}
	if out.Previous != expected {
		return out, fmt.Errorf("delivery conflict")
	}
	if err = os.Remove(filepath.Join(d.Root, "CURRENT")); err != nil && !os.IsNotExist(err) {
		return out, err
	}
	if err = syncDir(d.Root); err != nil {
		return out, err
	}
	out.RemovedSnapshots, err = d.prune("")
	return out, err
}

// PinPublished supports both a directly supplied snapshot and managed delivery.
// Publication locks prevent CURRENT/open/cleanup races, not unauthorized reads.
func (s Store) PinPublished(current *PublishedReader) (*PublishedReader, error) {
	actual := s
	if _, err := os.Stat(filepath.Join(s.Root, "DELIVERY")); err == nil {
		d := Delivery{s.Root}
		lock, err := d.lock(false)
		if err != nil {
			return nil, err
		}
		defer lock.Close()
		id, err := d.current()
		if err != nil {
			return nil, err
		}
		if id == "" {
			return nil, fmt.Errorf("publication withdrawn")
		}
		actual = Store{filepath.Join(s.Root, "snapshots", id)}
		if current != nil && current.View.ID == id {
			return current, nil
		}
		return actual.OpenPublished(id)
	} else if !os.IsNotExist(err) {
		return nil, err
	}
	id, err := s.Current()
	if err != nil {
		return nil, err
	}
	if current != nil && current.View.ID == id {
		return current, nil
	}
	return actual.OpenPublished(id)
}
