package sparse

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// RememberPublication records private resume checkpoints, not model-visible
// ancestry. Each released personal overlay is already a compact snapshot.
// Callers serialize this and CompactPublicationHistory with their publisher.
func (s Store) RememberPublication(id string) error {
	if !digestPattern.MatchString(id) {
		return fmt.Errorf("invalid history checkpoint")
	}
	heads, e := s.publicationHistory()
	if e != nil {
		return e
	}
	if len(heads) == 0 || heads[len(heads)-1] != id {
		heads = append(heads, id)
	}
	return s.writeHistory(heads)
}
func (s Store) publicationHistory() ([]string, error) {
	raw, e := os.ReadFile(filepath.Join(s.Root, "HISTORY.json"))
	if os.IsNotExist(e) {
		return nil, nil
	}
	if e != nil {
		return nil, e
	}
	var heads []string
	if e = json.Unmarshal(raw, &heads); e != nil {
		return nil, e
	}
	for _, h := range heads {
		if !digestPattern.MatchString(h) {
			return nil, fmt.Errorf("invalid history checkpoint")
		}
	}
	return heads, nil
}
func (s Store) writeHistory(heads []string) error {
	raw, e := json.Marshal(heads)
	if e != nil {
		return e
	}
	f, e := os.CreateTemp(s.Root, ".history-")
	if e != nil {
		return e
	}
	defer os.Remove(f.Name())
	defer f.Close()
	if _, e = f.Write(raw); e != nil {
		return e
	}
	if e = f.Sync(); e != nil {
		return e
	}
	if e = f.Close(); e != nil {
		return e
	}
	if e = os.Rename(f.Name(), filepath.Join(s.Root, "HISTORY.json")); e != nil {
		return e
	}
	return syncDir(s.Root)
}

// CompactPublicationHistory runs off the mutation path. It keeps the current
// snapshot and a bounded set of resume checkpoints, then removes unreachable
// objects. A pruned cursor gets the existing full-snapshot stream fallback.
// This only operates on publisher-private recipient history, never on a raw
// authoritative graph. The caller must exclude concurrent compilation.
func (s Store) CompactPublicationHistory(keep int) (int, error) {
	if keep < 2 {
		return 0, fmt.Errorf("at least two resume checkpoints required")
	}
	if _, e := os.Stat(filepath.Join(s.Root, "RECIPIENT")); e != nil {
		return 0, fmt.Errorf("recipient-private history required")
	}
	heads, e := s.publicationHistory()
	if e != nil {
		return 0, e
	}
	current, e := s.Current()
	if e != nil {
		return 0, e
	}
	if len(heads) > keep {
		heads = heads[len(heads)-keep:]
	}
	roots := append(append([]string{}, heads...), current)
	reachable := map[string]bool{}
	for _, head := range roots {
		for head != "" && !reachable[head] {
			m, e := s.manifest(head)
			if e != nil {
				return 0, e
			}
			if m.Previous != "" || m.Source != "authorized knowledge snapshot" {
				return 0, fmt.Errorf("not a compact recipient checkpoint")
			}
			reachable[head] = true
			reachable[m.Data] = true
			reachable[m.Index] = true
			head = m.Upstream
		}
	}
	// Persist the retained set first. A crash can leave extra objects but cannot
	// leave checkpoints pointing at deliberately removed objects.
	if e = s.writeHistory(heads); e != nil {
		return 0, e
	}
	entries, e := os.ReadDir(filepath.Join(s.Root, "objects"))
	if e != nil {
		return 0, e
	}
	removed := 0
	for _, entry := range entries {
		if !digestPattern.MatchString(entry.Name()) || reachable[entry.Name()] {
			continue
		}
		if e = os.Remove(filepath.Join(s.Root, "objects", entry.Name())); e != nil {
			return removed, e
		}
		removed++
	}
	return removed, syncDir(filepath.Join(s.Root, "objects"))
}
