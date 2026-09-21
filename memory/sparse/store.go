package sparse

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"syscall"
)

type Store struct{ Root string }

func digest(b []byte) string { h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }
func (s Store) object(hash string) (string, error) {
	if !digestPattern.MatchString(hash) {
		return "", fmt.Errorf("invalid object digest")
	}
	return filepath.Join(s.Root, "objects", hash), nil
}
func syncDir(path string) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	return f.Sync()
}

func (s Store) install(f *os.File, hash string) error {
	if err := f.Sync(); err != nil {
		return err
	}
	if err := f.Close(); err != nil {
		return err
	}
	path, err := s.object(hash)
	if err != nil {
		return err
	}
	if err = os.Link(f.Name(), path); err != nil && !os.IsExist(err) {
		return err
	}
	return syncDir(filepath.Dir(path))
}
func (s Store) put(b []byte) (string, error) {
	f, err := os.CreateTemp(filepath.Join(s.Root, "objects"), ".write-")
	if err != nil {
		return "", err
	}
	defer os.Remove(f.Name())
	defer f.Close()
	if _, err = f.Write(b); err != nil {
		return "", err
	}
	h := digest(b)
	return h, s.install(f, h)
}
func (s Store) read(hash string) ([]byte, error) {
	p, err := s.object(hash)
	if err != nil {
		return nil, err
	}
	b, err := os.ReadFile(p)
	if err == nil && digest(b) != hash {
		return nil, fmt.Errorf("object checksum mismatch: %s", hash)
	}
	return b, err
}
func (s Store) manifest(hash string) (Manifest, error) {
	return s.cachedManifest(hash)
}

// Build writes immutable content-addressed objects but does not publish them.
// Updates refer to their prior local layer AND the exact chosen upstream view.
func (s Store) Build(c ChangeSet) (string, error) {
	if !namespacePattern.MatchString(c.Namespace) || c.Generation == 0 || c.Source == "" || len(c.Coverage) == 0 {
		return "", fmt.Errorf("namespace, generation, source and coverage are required")
	}
	if c.Kind != "general" && c.Kind != "kb" && c.Kind != "server" {
		return "", fmt.Errorf("unknown layer kind")
	}
	if (c.Kind == "general") != (c.Upstream == "") {
		return "", fmt.Errorf("general must have no upstream; KB/server require upstream")
	}
	if c.Previous != "" {
		p, err := s.manifest(c.Previous)
		if err != nil {
			return "", err
		}
		if p.Namespace != c.Namespace || p.Kind != c.Kind || p.Generation >= c.Generation {
			return "", fmt.Errorf("previous layer identity or generation mismatch")
		}
	}
	if c.Upstream != "" {
		p, err := s.manifest(c.Upstream)
		if err != nil {
			return "", err
		}
		if (c.Kind == "kb" && p.Kind != "general") || (c.Kind == "server" && p.Kind != "general" && p.Kind != "kb") {
			return "", fmt.Errorf("invalid upstream layer kind")
		}
	}
	if err := os.MkdirAll(filepath.Join(s.Root, "objects"), 0700); err != nil {
		return "", err
	}
	f, err := os.CreateTemp(filepath.Join(s.Root, "objects"), ".records-")
	if err != nil {
		return "", err
	}
	defer os.Remove(f.Name())
	defer f.Close()
	h := sha256.New()
	writer := io.MultiWriter(f, h)
	idx := Index{Postings: map[string][]int{}}
	seen := map[string]bool{}
	var offset int64
	for _, r := range c.Records {
		if err := validateRecord(r, c.Namespace, c.Kind); err != nil {
			return "", err
		}
		if seen[r.ID] {
			return "", fmt.Errorf("duplicate record ID: %s", r.ID)
		}
		seen[r.ID] = true
		b, err := json.Marshal(r)
		if err != nil {
			return "", err
		}
		b = append(b, '\n')
		if len(b) > 16<<20 {
			return "", fmt.Errorf("record exceeds 16 MiB codec limit")
		}
		e := Entry{Ref: r.Ref, Offset: offset, Length: len(b), SHA256: digest(b), Scope: r.Scope, Lifecycle: r.Lifecycle, Suppressed: r.Suppressed, Confidence: r.Confidence, ValidFrom: r.ValidFrom, ValidUntil: r.ValidUntil, Redirect: r.Redirect, Edges: r.Edges}
		n := len(idx.Entries)
		idx.Entries = append(idx.Entries, e)
		text := r.Key + " " + r.Content
		for _, alias := range r.Aliases {
			text += " " + alias
		}
		for _, term := range Terms(text) {
			idx.Postings[term] = append(idx.Postings[term], n)
		}
		if _, err = writer.Write(b); err != nil {
			return "", err
		}
		offset += int64(len(b))
	}
	for _, r := range c.Delete {
		if err := validateRef(r); err != nil {
			return "", err
		}
		if r.Namespace != c.Namespace || seen[r.ID] {
			return "", fmt.Errorf("delete must address a distinct record owned by this layer")
		}
		seen[r.ID] = true
	}
	for _, r := range c.Suppressions {
		if err := validateRef(r.Target); err != nil {
			return "", err
		}
		if r.Reason == "" {
			return "", fmt.Errorf("suppression needs an authoritative reason")
		}
	}
	dataHash := hex.EncodeToString(h.Sum(nil))
	if err = s.install(f, dataHash); err != nil {
		return "", err
	}
	b, err := json.Marshal(idx)
	if err != nil {
		return "", err
	}
	indexHash, err := s.put(b)
	if err != nil {
		return "", err
	}
	m := Manifest{Serving: c.Serving, Authorization: c.Authorization, ReadContracts: c.ReadContracts, Format: FormatVersion, Namespace: c.Namespace, Kind: c.Kind, Generation: c.Generation, Previous: c.Previous, Upstream: c.Upstream, Data: dataHash, Index: indexHash, Delete: c.Delete, Suppressions: c.Suppressions, Source: c.Source, Coverage: c.Coverage}
	b, err = json.Marshal(m)
	if err != nil {
		return "", err
	}
	id, err := s.put(b)
	if err != nil {
		return "", err
	}
	v, err := s.Open(id)
	if err != nil {
		return "", err
	}
	v.Close()
	return id, nil
}

func (s Store) Current() (string, error) {
	b, err := os.ReadFile(filepath.Join(s.Root, "CURRENT"))
	if err != nil {
		return "", err
	}
	var head struct {
		View string `json:"view"`
	}
	if err = json.Unmarshal(b, &head); err != nil {
		return "", err
	}
	if !digestPattern.MatchString(head.View) {
		return "", fmt.Errorf("invalid current view")
	}
	return head.View, nil
}

// Publish uses compare-and-swap plus atomic rename. Existing readers retain
// their immutable generation; a failed publication cannot alter CURRENT.
func (s Store) Publish(id, expected string) error {
	v, err := s.Open(id)
	if err != nil {
		return err
	}
	defer v.Close()
	lock, err := os.OpenFile(filepath.Join(s.Root, ".publish.lock"), os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return err
	}
	defer lock.Close()
	if err = syscall.Flock(int(lock.Fd()), syscall.LOCK_EX); err != nil {
		return err
	}
	defer syscall.Flock(int(lock.Fd()), syscall.LOCK_UN)
	old, err := s.Current()
	if err != nil && !os.IsNotExist(err) {
		return err
	}
	if old != expected {
		return fmt.Errorf("publication conflict: CURRENT changed")
	}
	f, err := os.CreateTemp(s.Root, ".current-")
	if err != nil {
		return err
	}
	defer os.Remove(f.Name())
	defer f.Close()
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
	if err = os.Rename(f.Name(), filepath.Join(s.Root, "CURRENT")); err != nil {
		return err
	}
	return syncDir(s.Root)
}
