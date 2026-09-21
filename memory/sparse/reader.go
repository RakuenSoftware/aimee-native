package sparse

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"iter"
	"math"
	"os"
	"path/filepath"
	"sort"
	"sync/atomic"
	"time"
)

type location struct {
	entry   Entry
	file    *os.File
	segment string
}
type View struct {
	refs          atomic.Int64
	base          *View
	basePublished *PublishedReader
	reads         map[string]ReadContract
	ID            string
	Layers        []Manifest
	records       map[string]*location
	postings      map[string][]string
	files         []*os.File
	hidden        map[string][]Scope
}

func (v *View) Close() {
	if v.refs.Add(-1) != 0 {
		return
	}
	if v.base != nil {
		v.base.Close()
	}
	for _, f := range v.files {
		f.Close()
	}
	v.files = nil
}

// Open loads only manifests and indexes into RAM. Record bodies remain in the
// immutable disk objects and are read by offset on demand.
func (v *View) record(key string) *location {
	if r := v.records[key]; r != nil {
		return r
	}
	if v.base != nil {
		return v.base.record(key)
	}
	return nil
}
func (v *View) allRecords() iter.Seq2[string, *location] {
	return func(yield func(string, *location) bool) {
		if v.base != nil {
			for k, r := range v.base.allRecords() {
				if !yield(k, r) {
					return
				}
			}
		}
		for k, r := range v.records {
			if !yield(k, r) {
				return
			}
		}
	}
}
func (v *View) namespaceRecords(namespace string) iter.Seq2[string, *location] {
	if len(v.Layers) > 0 && v.Layers[len(v.Layers)-1].Namespace != namespace && v.base != nil {
		return v.base.namespaceRecords(namespace)
	}
	return func(yield func(string, *location) bool) {
		for k, r := range v.records {
			if r.entry.Namespace == namespace && !yield(k, r) {
				return
			}
		}
	}
}
func (s Store) Open(id string) (*View, error) {
	m, e := s.manifest(id)
	if e != nil {
		return nil, e
	}
	if m.Serving != nil && m.Serving.Version == 2 {
		return s.openOverlay(id, m)
	}
	return s.openRaw(id, false)
}
func (s Store) openRaw(id string, localOnly bool) (*View, error) {
	v := &View{ID: id, records: map[string]*location{}, postings: map[string][]string{}, hidden: map[string][]Scope{}}
	v.refs.Store(1)
	segments := map[string]Index{}
	seen := map[string]bool{}
	namespaces := map[string]bool{}
	var load func(string) error
	load = func(head string) error {
		m, err := s.manifest(head)
		if err != nil {
			return err
		}
		if namespaces[m.Namespace] {
			return fmt.Errorf("namespace reused across authority layers")
		}
		namespaces[m.Namespace] = true
		if m.Kind != "general" && m.Kind != "kb" && m.Kind != "server" {
			return fmt.Errorf("unknown layer kind")
		}
		if (m.Kind == "general") != (m.Upstream == "") {
			return fmt.Errorf("invalid layer root")
		}
		if m.Upstream != "" && !localOnly {
			parent, err := s.manifest(m.Upstream)
			if err != nil {
				return err
			}
			if (m.Kind == "kb" && parent.Kind != "general") || (m.Kind == "server" && parent.Kind != "general" && parent.Kind != "kb") {
				return fmt.Errorf("invalid source lineage")
			}
			if err = load(m.Upstream); err != nil {
				return err
			}
		}
		var chain []struct {
			id string
			m  Manifest
		}
		for current := head; current != ""; {
			if seen[current] || len(seen) >= 4096 {
				return fmt.Errorf("cyclic or excessive image ancestry")
			}
			seen[current] = true
			x, err := s.manifest(current)
			if err != nil {
				return err
			}
			if x.Namespace != m.Namespace || x.Kind != m.Kind {
				return fmt.Errorf("delta authority mismatch")
			}
			if len(chain) > 0 && x.Generation >= chain[len(chain)-1].m.Generation {
				return fmt.Errorf("delta generation not increasing")
			}
			chain = append(chain, struct {
				id string
				m  Manifest
			}{current, x})
			current = x.Previous
		}
		resolutions := map[string]Suppression{}
		for n := len(chain) - 1; n >= 0; n-- {
			x := chain[n]
			raw, err := s.read(x.m.Index)
			if err != nil {
				return err
			}
			var idx Index
			if err = json.Unmarshal(raw, &idx); err != nil {
				return err
			}
			path, err := s.object(x.m.Data)
			if err != nil {
				return err
			}
			f, err := os.Open(path)
			if err != nil {
				return err
			}
			v.files = append(v.files, f)
			stat, err := f.Stat()
			if err != nil {
				return err
			}
			localIDs := map[string]bool{}
			for _, e := range idx.Entries {
				if err := validateRef(e.Ref); err != nil {
					return err
				}
				if e.Namespace != m.Namespace || localIDs[e.Key()] || e.Length <= 0 || e.Length > 16<<20 || e.Offset < 0 || e.Offset > stat.Size()-int64(e.Length) || !digestPattern.MatchString(e.SHA256) {
					return fmt.Errorf("invalid record directory")
				}
				localIDs[e.Key()] = true
				// Check indexed policy fields with the same codec used by the writer.
				r := Record{Ref: e.Ref, Scope: e.Scope, Confidence: e.Confidence, Lifecycle: e.Lifecycle, ValidFrom: e.ValidFrom, ValidUntil: e.ValidUntil, Redirect: e.Redirect, Edges: e.Edges}
				if err := validateRecord(r, m.Namespace, m.Kind); err != nil {
					return err
				}
				if old := v.records[e.Key()]; old != nil && old.entry.Revision == e.Revision && old.entry.SHA256 != e.SHA256 {
					return fmt.Errorf("content changed without a new revision")
				}
				v.records[e.Key()] = &location{e, f, x.id}
			}
			for term, postings := range idx.Postings {
				if term == "" {
					return fmt.Errorf("empty index term")
				}
				for _, i := range postings {
					if i < 0 || i >= len(idx.Entries) {
						return fmt.Errorf("posting outside record directory")
					}
				}
			}
			segments[x.id] = idx
			for _, ref := range x.m.Delete {
				old := v.records[ref.Key()]
				if ref.Namespace != m.Namespace || old == nil || old.entry.Revision != ref.Revision {
					return fmt.Errorf("stale or foreign tombstone: %s", ref.Key())
				}
				delete(v.records, ref.Key())
			}
			for _, r := range x.m.Suppressions {
				if r.Reason == "" || r.Target.Namespace == m.Namespace {
					return fmt.Errorf("invalid upstream suppression")
				}
				if err := validateRecord(Record{Ref: Ref{Namespace: m.Namespace, ID: "resolution", Revision: "1"}, Scope: r.Scope, Lifecycle: "active"}, m.Namespace, m.Kind); err != nil {
					return err
				}
				resolutionKey := r.Target.Key() + "/" + r.Scope.Key()
				if r.Release {
					delete(resolutions, resolutionKey)
				} else {
					resolutions[resolutionKey] = r
				}
			}
		}
		for _, r := range resolutions {
			key := r.Target.Key()
			target := v.records[key]
			if target == nil || target.entry.Revision != r.Target.Revision {
				return fmt.Errorf("upstream resolution needs reconciliation: %s", key)
			}
			v.hidden[key] = append(v.hidden[key], r.Scope)
		}
		v.Layers = append(v.Layers, m)
		return nil
	}
	if err := load(id); err != nil {
		v.Close()
		return nil, err
	}
	// Build a view index without obsolete versions or physically duplicating data.
	for segment, idx := range segments {
		for term, postings := range idx.Postings {
			for _, i := range postings {
				key := idx.Entries[i].Key()
				loc := v.records[key]
				if loc != nil && loc.segment == segment {
					v.postings[term] = append(v.postings[term], key)
				}
			}
		}
	}
	for key, loc := range v.records {
		if loc.entry.Redirect != nil {
			if _, err := v.resolve(key); err != nil {
				v.Close()
				return nil, err
			}
		}
	}
	tip, err := s.manifest(id)
	if err == nil {
		err = v.loadContracts(tip.ReadContracts)
	}
	if err != nil {
		v.Close()
		return nil, err
	}
	return v, nil
}

func (v *View) isHidden(key string, grants map[string]bool) bool {
	for _, scope := range v.hidden[key] {
		if scope == (Scope{"global", "_global"}) || grants[scope.Key()] {
			return true
		}
	}
	return false
}

func (v *View) visibleChain(key string, grants map[string]bool, now time.Time) bool {
	for range 64 {
		loc := v.record(key)
		if loc == nil || v.isHidden(key, grants) || !eligible(loc.entry, grants, now) {
			return false
		}
		if loc.entry.Redirect == nil {
			return true
		}
		key = loc.entry.Redirect.Key()
	}
	return false
}

func (v *View) resolve(key string) (*location, error) {
	seen := map[string]bool{}
	for i := 0; i < 64; i++ {
		if seen[key] {
			return nil, fmt.Errorf("dedup redirect cycle")
		}
		seen[key] = true
		loc := v.record(key)
		if loc == nil {
			return nil, fmt.Errorf("record not found: %s", key)
		}
		ref := loc.entry.Redirect
		if ref == nil {
			return loc, nil
		}
		next := v.record(ref.Key())
		if next == nil || next.entry.Revision != ref.Revision {
			return nil, fmt.Errorf("stale dedup redirect")
		}
		key = ref.Key()
	}
	return nil, fmt.Errorf("redirect chain too deep")
}

func eligible(e Entry, grants map[string]bool, now time.Time) bool {
	if e.Lifecycle != "active" || e.Suppressed {
		return false
	}
	if e.Scope != (Scope{"global", "_global"}) && !grants[e.Scope.Key()] {
		return false
	}
	if e.ValidFrom != "" {
		t, err := time.Parse(time.RFC3339Nano, e.ValidFrom)
		if err != nil || now.Before(t) {
			return false
		}
	}
	if e.ValidUntil != "" {
		t, err := time.Parse(time.RFC3339Nano, e.ValidUntil)
		if err != nil || !now.Before(t) {
			return false
		}
	}
	return true
}

func (v *View) read(loc *location) (Record, error) {
	e := loc.entry
	b := make([]byte, e.Length)
	_, err := loc.file.ReadAt(b, e.Offset)
	if err != nil {
		return Record{}, err
	}
	if digest(b) != e.SHA256 {
		return Record{}, fmt.Errorf("record checksum mismatch: %s", e.Key())
	}
	var r Record
	if err = json.Unmarshal(b, &r); err != nil {
		return r, err
	}
	if r.Ref != e.Ref {
		return r, fmt.Errorf("record identity mismatch")
	}
	return r, nil
}

func (v *View) Get(ref Ref, grants map[string]bool, now time.Time) (Record, error) {
	loc := v.record(ref.Key())
	if loc == nil || loc.entry.Revision != ref.Revision || !v.visibleChain(ref.Key(), grants, now) {
		return Record{}, fmt.Errorf("record unavailable")
	}
	loc, err := v.resolve(ref.Key())
	if err != nil {
		return Record{}, err
	}
	if v.isHidden(loc.entry.Key(), grants) || !eligible(loc.entry, grants, now) {
		return Record{}, fmt.Errorf("canonical record unavailable")
	}
	return v.read(loc)
}

type SearchResult struct {
	View          string   `json:"view"`
	Records       []Record `json:"records"`
	Candidates    int      `json:"candidates"`
	BytesRead     int      `json:"bytes_read"`
	ElapsedMicros int64    `json:"elapsed_us"`
	Signals       []string `json:"signals"`
}

// Search is an explicitly lexical first serving codec. Its candidate budget
// fails visibly instead of silently returning a biased subset of a broad query.
func (v *View) Search(query string, limit, budget int, grants map[string]bool, now time.Time) (SearchResult, error) {
	start := time.Now()
	result := SearchResult{View: v.ID, Records: []Record{}, Signals: []string{"lexical-v1"}}
	terms := Terms(query)
	if len(terms) == 0 || limit < 1 || limit > 128 || budget < limit {
		return result, fmt.Errorf("invalid search parameters")
	}
	scores := map[string]float64{}
	for _, term := range terms {
		postings := v.postings[term]
		if v.base != nil {
			postings = append(append([]string{}, v.base.postings[term]...), postings...)
		}
		weight := math.Log1p(float64(v.recordCount()) / float64(1+len(postings)))
		termSeen := map[string]bool{}
		for _, key := range postings {
			if !v.visibleChain(key, grants, now) {
				continue
			}
			loc, err := v.resolve(key)
			if err != nil {
				return result, err
			}
			canonical := loc.entry.Key()
			if v.isHidden(canonical, grants) || !eligible(loc.entry, grants, now) {
				continue
			}
			if termSeen[canonical] {
				continue
			}
			termSeen[canonical] = true
			// Aliases are alternate addresses, not additional votes for a record.
			if scores[canonical] == 0 && len(scores) >= budget {
				return result, fmt.Errorf("lexical candidate budget exceeded; refine query")
			}
			scores[canonical] += weight
		}
	}
	type hit struct {
		key   string
		score float64
	}
	hits := make([]hit, 0, len(scores))
	for key, score := range scores {
		hits = append(hits, hit{key, score})
	}
	sort.Slice(hits, func(i, j int) bool {
		if hits[i].score != hits[j].score {
			return hits[i].score > hits[j].score
		}
		a, b := v.record(hits[i].key).entry, v.record(hits[j].key).entry
		if a.Confidence != b.Confidence {
			return a.Confidence > b.Confidence
		}
		return hits[i].key < hits[j].key
	})
	result.Candidates = len(hits)
	if len(hits) > limit {
		hits = hits[:limit]
	}
	for _, h := range hits {
		loc := v.record(h.key)
		r, err := v.read(loc)
		if err != nil {
			return result, err
		}
		result.Records = append(result.Records, r)
		result.BytesRead += loc.entry.Length
	}
	result.ElapsedMicros = time.Since(start).Microseconds()
	return result, nil
}

// Neighbors preserves explicit, versioned graph links and enforces scope at
// each hop. Missing/stale targets are surfaced, never replaced by a newer fact.
func (v *View) Neighbors(ref Ref, grants map[string]bool, now time.Time) ([]Record, error) {
	r, err := v.Get(ref, grants, now)
	if err != nil {
		return nil, err
	}
	out := []Record{}
	for _, edge := range r.Edges {
		target, err := v.Get(edge.Target, grants, now)
		if err != nil {
			return nil, fmt.Errorf("edge %s: %w", edge.Relation, err)
		}
		out = append(out, target)
	}
	return out, nil
}

// Verify explicitly reads the entire reachable payload. Normal open/search
// validate metadata and only the payload records actually consumed.
func (v *View) Verify() error {
	if v.base != nil {
		if err := v.base.Verify(); err != nil {
			return err
		}
	}
	return v.verifyLocal()
}
func (v *View) verifyLocal() error {
	for _, loc := range v.records {
		if _, err := v.read(loc); err != nil {
			return err
		}
	}
	for _, f := range v.files {
		stat, err := f.Stat()
		if err != nil {
			return err
		}
		h := sha256.New()
		if _, err := io.Copy(h, io.NewSectionReader(f, 0, stat.Size())); err != nil {
			return err
		}
		if hex.EncodeToString(h.Sum(nil)) != filepath.Base(f.Name()) {
			return fmt.Errorf("data object checksum mismatch")
		}
	}
	return nil
}

func (v *View) recordCount() int {
	n := len(v.records)
	if v.base != nil {
		n += v.base.recordCount()
	}
	return n
}
