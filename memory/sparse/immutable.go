package sparse

// These caches reuse parsing and validation, never an authorization decision.
// Objects must remain publisher-owned and immutable. File identity, size,
// modification AND change time are checked even when a digest is already known.
// A new inode or any metadata change requires a fresh SHA-256 verification.
import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"sync"
	"syscall"
)

type objectStamp struct {
	Device, Inode     uint64
	Size              int64
	Modified, Changed syscall.Timespec
}

func stamp(f *os.File) (objectStamp, error) {
	info, e := f.Stat()
	if e != nil {
		return objectStamp{}, e
	}
	if !info.Mode().IsRegular() {
		return objectStamp{}, fmt.Errorf("object must be a regular file")
	}
	st := info.Sys().(*syscall.Stat_t)
	return objectStamp{uint64(st.Dev), st.Ino, st.Size, st.Mtim, st.Ctim}, nil
}

var verifiedObjects = struct {
	sync.Mutex
	entries map[objectStamp]string
}{entries: map[objectStamp]string{}}

func verifyObject(f *os.File, hash string) error {
	before, e := stamp(f)
	if e != nil {
		return e
	}
	verifiedObjects.Lock()
	known := verifiedObjects.entries[before] == hash
	verifiedObjects.Unlock()
	if known {
		return nil
	}
	h := sha256.New()
	if _, e = io.Copy(h, io.NewSectionReader(f, 0, before.Size)); e != nil {
		return e
	}
	after, e := stamp(f)
	if e != nil {
		return e
	}
	if after != before || hex.EncodeToString(h.Sum(nil)) != hash {
		return fmt.Errorf("object checksum mismatch: %s", hash)
	}
	verifiedObjects.Lock()
	defer verifiedObjects.Unlock()
	if len(verifiedObjects.entries) >= 4096 {
		clear(verifiedObjects.entries)
	}
	verifiedObjects.entries[after] = hash
	return nil
}
func (s Store) verifyObject(hash string) error {
	path, e := s.object(hash)
	if e != nil {
		return e
	}
	f, e := os.Open(path)
	if e != nil {
		return e
	}
	defer f.Close()
	return verifyObject(f, hash)
}

// Only general manifests are retained: recipient metadata is not a global cache.
var generalManifests = struct {
	sync.Mutex
	entries map[string]Manifest
}{entries: map[string]Manifest{}}

func (s Store) cachedManifest(hash string) (Manifest, error) {
	generalManifests.Lock()
	m, ok := generalManifests.entries[hash]
	generalManifests.Unlock()
	if ok {
		return m, s.verifyObject(hash)
	}
	raw, e := s.read(hash)
	if e != nil {
		return m, e
	}
	if e = json.Unmarshal(raw, &m); e != nil {
		return m, e
	}
	if m.Format != FormatVersion || !namespacePattern.MatchString(m.Namespace) || m.Generation == 0 || m.Source == "" {
		return m, fmt.Errorf("incompatible image manifest")
	}
	if m.Kind == "general" && m.Previous == "" && m.Serving != nil && m.Source == "authorized knowledge snapshot" {
		generalManifests.Lock()
		if len(generalManifests.entries) >= 2 {
			clear(generalManifests.entries)
		}
		generalManifests.entries[hash] = m
		generalManifests.Unlock()
	}
	return m, nil
}

var generalReaders = struct {
	sync.Mutex
	entries map[string]*PublishedReader
}{entries: map[string]*PublishedReader{}}

func (s Store) openGeneral(id string) (*PublishedReader, error) {
	generalReaders.Lock()
	defer generalReaders.Unlock()
	if p := generalReaders.entries[id]; p != nil {
		m := p.View.Layers[0]
		for _, h := range []string{id, m.Data, m.Index} {
			if e := s.verifyObject(h); e != nil {
				return nil, e
			}
		}
		// Verify the pinned data inode too: a path replacement must not hide a
		// mutation of the old file still referenced by cached locations.
		for _, f := range p.View.files {
			if e := verifyObject(f, m.Data); e != nil {
				return nil, e
			}
		}
		p.View.refs.Add(1)
		return p, nil
	}
	p, e := s.openPublishedRaw(id)
	if e != nil {
		return nil, e
	}
	if len(p.View.Layers) != 1 || p.View.Layers[0].Kind != "general" {
		p.Close()
		return nil, fmt.Errorf("immutable general base required")
	}
	for _, loc := range p.View.records {
		if loc.entry.Scope != (Scope{"global", "_global"}) {
			p.Close()
			return nil, fmt.Errorf("general cache must contain public records only")
		}
	}
	if len(generalReaders.entries) >= 2 {
		for key, old := range generalReaders.entries {
			delete(generalReaders.entries, key)
			old.Close()
			break
		}
	}
	generalReaders.entries[id] = p
	p.View.refs.Add(1)
	return p, nil
}

// Version 2 is an immutable, already released public base plus an independently
// bound personal snapshot. It inherits base routing without serializing it into
// the overlay. No raw graph ancestry, tombstones or cross-layer policy mutations
// are accepted here: those must be resolved by Aimee before release.
func (s Store) openOverlay(id string, m Manifest) (_ *View, err error) {
	if m.Kind != "server" || m.Previous != "" || m.Upstream == "" || m.Authorization == "" || m.Source != "authorized knowledge snapshot" || len(m.Delete)+len(m.Suppressions) != 0 || len(m.Serving.ReferenceLookups) != 0 {
		return nil, fmt.Errorf("invalid recipient overlay")
	}
	base, e := s.openGeneral(m.Upstream)
	if e != nil {
		return nil, e
	}
	if base.View.Layers[0].Namespace == m.Namespace {
		base.Close()
		return nil, fmt.Errorf("namespace reused across authority layers")
	}
	v, e := s.openRaw(id, true)
	if e != nil {
		base.Close()
		return nil, e
	}
	v.base = base.View
	v.basePublished = base
	v.Layers = append(append([]Manifest{}, base.View.Layers...), m)
	return v, nil
}

// DropPublishedCaches releases cache-owned leases when a serving process loses
// its publication. Existing pinned views still require Close; callers must stop
// serving them. This is cache disposal, never a replacement authorization gate.
func DropPublishedCaches() {
	generalReaders.Lock()
	for id, p := range generalReaders.entries {
		delete(generalReaders.entries, id)
		p.Close()
	}
	generalReaders.Unlock()
	generalManifests.Lock()
	clear(generalManifests.entries)
	generalManifests.Unlock()
}
