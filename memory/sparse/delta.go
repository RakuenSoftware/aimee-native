package sparse

// Recipient deltas contain only already-released canonical records. Raw source
// ancestry must never be used as a recipient update protocol.
import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"sort"
)

type CueInsert struct {
	Position int          `json:"position"`
	Cue      ReferenceCue `json:"cue"`
}

type RecordDelta struct {
	ReuseLayer   string         `json:"reuse_layer,omitempty"`
	CueInsert    []CueInsert    `json:"cue_insert,omitempty"`
	CueRemove    []ReferenceCue `json:"cue_remove,omitempty"`
	Manifest     Manifest       `json:"manifest"`
	ReuseServing bool           `json:"reuse_serving,omitempty"`
	ReuseReads   bool           `json:"reuse_reads,omitempty"`
	Upsert       []Record       `json:"upsert,omitempty"`
	Remove       []Ref          `json:"remove,omitempty"`
	// Noncanonical legacy order is sent only when that layer must be rebuilt.
	Order []string `json:"order,omitempty"`
}
type PublicationDelta struct {
	Version int           `json:"version"`
	Base    string        `json:"base"`
	Target  string        `json:"target"`
	Layers  []RecordDelta `json:"layers"`
}

// DiffPublished requires immutable, previously authorized recipient snapshots.
// The caller authenticates the recipient before selecting either snapshot.
func DiffPublished(previous *PublishedReader, current *PublishedReader) (PublicationDelta, error) {
	d := PublicationDelta{Version: 1, Target: current.View.ID}
	if current.View.base != nil {
		d.Version = 2
	}
	old := map[string]Manifest{}
	if previous != nil {
		d.Base = previous.View.ID
		for _, m := range previous.View.Layers {
			old[m.Namespace] = m
		}
	}
	for _, m := range current.View.Layers {
		if current.View.base != nil && previous != nil && previous.View.base != nil && current.View.base.ID == previous.View.base.ID && m.Kind == "general" {
			d.Layers = append(d.Layers, RecordDelta{ReuseLayer: current.View.base.ID})
			continue
		}
		x := RecordDelta{Manifest: m}
		prior, exists := old[m.Namespace]
		if exists && reflect.DeepEqual(m.Serving, prior.Serving) {
			x.ReuseServing = true
			x.Manifest.Serving = nil
		}
		if exists && m.Serving != nil && prior.Serving != nil && !x.ReuseServing {
			oldMeta, newMeta := *prior.Serving, *m.Serving
			oldMeta.ReferenceCues = nil
			newMeta.ReferenceCues = nil
			if reflect.DeepEqual(oldMeta, newMeta) {
				before, after := map[ReferenceCue]bool{}, map[ReferenceCue]bool{}
				for _, c := range prior.Serving.ReferenceCues {
					before[c] = true
				}
				for _, c := range m.Serving.ReferenceCues {
					after[c] = true
				}
				for _, c := range prior.Serving.ReferenceCues {
					if !after[c] {
						x.CueRemove = append(x.CueRemove, c)
					}
				}
				for i, c := range m.Serving.ReferenceCues {
					if !before[c] {
						x.CueInsert = append(x.CueInsert, CueInsert{i, c})
					}
				}
				reconstructed, e := patchCues(prior.Serving.ReferenceCues, x.CueRemove, x.CueInsert)
				if e == nil && reflect.DeepEqual(reconstructed, m.Serving.ReferenceCues) {
					x.ReuseServing = true
					x.Manifest.Serving = nil
				} else {
					x.CueRemove = nil
					x.CueInsert = nil
				}
			}
		}
		if exists && reflect.DeepEqual(m.ReadContracts, prior.ReadContracts) {
			x.ReuseReads = true
			x.Manifest.ReadContracts = nil
		}
		changed := !exists || m.Data != prior.Data || m.Index != prior.Index
		if changed {
			var ordered []*location
			for _, loc := range current.View.namespaceRecords(m.Namespace) {
				if loc.entry.Namespace == m.Namespace {
					ordered = append(ordered, loc)
				}
			}
			sort.Slice(ordered, func(i, j int) bool { return ordered[i].entry.Offset < ordered[j].entry.Offset })
			order := []string{}
			for _, loc := range ordered {
				order = append(order, loc.entry.ID)
				var before *location
				if previous != nil {
					before = previous.View.record(loc.entry.Ref.Key())
				}
				if before == nil || before.entry.SHA256 != loc.entry.SHA256 {
					r, e := current.View.read(loc)
					if e != nil {
						return d, e
					}
					x.Upsert = append(x.Upsert, r)
				}
			}
			if !sort.StringsAreSorted(order) {
				x.Order = order
			}
			if previous != nil {
				for key, loc := range previous.View.namespaceRecords(m.Namespace) {
					if loc.entry.Namespace == m.Namespace && current.View.record(key) == nil {
						x.Remove = append(x.Remove, loc.entry.Ref)
					}
				}
			}
			sort.Slice(x.Remove, func(i, j int) bool { return x.Remove[i].ID < x.Remove[j].ID })
		}
		d.Layers = append(d.Layers, x)
	}
	return d, nil
}

// MaterializeDelta stages privately. It does not change a reader's CURRENT.
// The target's content digest commits all records, ordering and routing metadata;
// malformed, missing or tampered operations cannot produce that target digest.
func MaterializeDelta(previous Store, dst Store, d PublicationDelta) (err error) {
	if (d.Version != 1 && d.Version != 2) || !digestPattern.MatchString(d.Target) || (d.Base != "" && !digestPattern.MatchString(d.Base)) || len(d.Layers) < 1 || len(d.Layers) > 3 {
		return fmt.Errorf("invalid publication delta")
	}
	if err = os.Mkdir(dst.Root, 0700); err != nil {
		return err
	}
	defer func() {
		if err != nil {
			os.RemoveAll(dst.Root)
		}
	}()
	if err = os.Mkdir(filepath.Join(dst.Root, "objects"), 0700); err != nil {
		return err
	}
	var old *PublishedReader
	prior := map[string]Manifest{}
	if d.Base != "" {
		old, err = previous.OpenPublished(d.Base)
		if err != nil {
			return err
		}
		defer old.Close()
		for _, m := range old.View.Layers {
			prior[m.Namespace] = m
		}
	}
	head := ""
	seen := map[string]bool{}
	for _, x := range d.Layers {
		if x.ReuseLayer != "" {
			if d.Version != 2 || old == nil || old.View.base == nil || old.View.base.ID != x.ReuseLayer || head != "" {
				return fmt.Errorf("invalid immutable base reuse")
			}
			check := x
			check.ReuseLayer = ""
			raw, _ := json.Marshal(check)
			empty, _ := json.Marshal(RecordDelta{})
			if string(raw) != string(empty) {
				return fmt.Errorf("operations on reused base")
			}
			m, e := previous.manifest(x.ReuseLayer)
			if e != nil {
				return e
			}
			if m.Kind != "general" || m.Previous != "" {
				return fmt.Errorf("invalid reused base")
			}
			for _, h := range []string{x.ReuseLayer, m.Data, m.Index} {
				src, _ := previous.object(h)
				dest, _ := dst.object(h)
				if e = os.Link(src, dest); e != nil && !os.IsExist(e) {
					return e
				}
			}
			seen[m.Namespace] = true
			head = x.ReuseLayer
			continue
		}
		m := x.Manifest
		if seen[m.Namespace] || m.Previous != "" || m.Upstream != head || m.Source != "authorized knowledge snapshot" || len(m.Delete) != 0 || len(m.Suppressions) != 0 {
			return fmt.Errorf("invalid recipient lineage")
		}
		seen[m.Namespace] = true
		before, exists := prior[m.Namespace]
		if x.ReuseServing {
			if !exists || m.Serving != nil {
				return fmt.Errorf("invalid serving reuse")
			}
			m.Serving = before.Serving
			if len(x.CueRemove)+len(x.CueInsert) > 0 {
				if m.Serving == nil {
					return fmt.Errorf("missing cue predecessor")
				}
				next := *m.Serving
				next.ReferenceCues, err = patchCues(m.Serving.ReferenceCues, x.CueRemove, x.CueInsert)
				if err != nil {
					return err
				}
				m.Serving = &next
			}
		}
		if !x.ReuseServing && len(x.CueRemove)+len(x.CueInsert) > 0 {
			return fmt.Errorf("invalid cue patch")
		}
		if x.ReuseReads {
			if !exists || m.ReadContracts != nil {
				return fmt.Errorf("invalid read reuse")
			}
			m.ReadContracts = before.ReadContracts
		}
		if exists && m.Data == before.Data && m.Index == before.Index {
			if len(x.Upsert)+len(x.Remove)+len(x.Order) != 0 {
				return fmt.Errorf("operations on unchanged layer")
			}
			for _, h := range []string{m.Data, m.Index} {
				src, e := previous.object(h)
				if e != nil {
					return e
				}
				dest, _ := dst.object(h)
				if e = os.Link(src, dest); e != nil && !os.IsExist(e) {
					return e
				}
			}
		} else {
			records := map[string]Record{}
			if old != nil {
				for _, loc := range old.View.namespaceRecords(m.Namespace) {
					if loc.entry.Namespace == m.Namespace {
						r, e := old.View.read(loc)
						if e != nil {
							return e
						}
						records[r.ID] = r
					}
				}
			}
			touched := map[string]bool{}
			for _, ref := range x.Remove {
				r, ok := records[ref.ID]
				if !ok || r.Ref != ref || touched[ref.ID] {
					return fmt.Errorf("invalid removal")
				}
				delete(records, ref.ID)
				touched[ref.ID] = true
			}
			for _, r := range x.Upsert {
				if r.Namespace != m.Namespace || touched[r.ID] {
					return fmt.Errorf("invalid upsert")
				}
				touched[r.ID] = true
				records[r.ID] = r
			}
			order := x.Order
			if order == nil {
				for id := range records {
					order = append(order, id)
				}
				sort.Strings(order)
			}
			if len(order) != len(records) {
				return fmt.Errorf("incomplete record order")
			}
			rows := []Record{}
			for _, id := range order {
				r, ok := records[id]
				if !ok {
					return fmt.Errorf("invalid record order")
				}
				rows = append(rows, r)
				delete(records, id)
			}
			built, e := dst.Build(ChangeSet{Serving: m.Serving, Authorization: m.Authorization, ReadContracts: m.ReadContracts, Namespace: m.Namespace, Kind: m.Kind, Generation: m.Generation, Upstream: m.Upstream, Records: rows, Source: m.Source, Coverage: m.Coverage})
			if e != nil {
				return e
			}
			raw, _ := json.Marshal(m)
			if built != digest(raw) {
				return fmt.Errorf("delta target layer integrity failed")
			}
		}
		raw, _ := json.Marshal(m)
		head, err = dst.put(raw)
		if err != nil {
			return err
		}
	}
	if head != d.Target {
		return fmt.Errorf("delta target integrity failed")
	}
	check, e := dst.OpenPublished(head)
	if e != nil {
		return e
	}
	check.Close()
	return dst.Publish(head, "")
}

// ApplyDelta provides crash-safe compare-and-swap and idempotent replay. Bad
// transfers do not expose partial data. Network authorization failures are
// handled by the fetcher, which withdraws the recipient's delivery.
func (d Delivery) ApplyDelta(delta PublicationDelta, gid int) (PublicationResult, error) {
	if (delta.Version != 1 && delta.Version != 2) || !digestPattern.MatchString(delta.Target) || (delta.Base != "" && !digestPattern.MatchString(delta.Base)) {
		return PublicationResult{}, fmt.Errorf("invalid delta envelope")
	}
	if e := d.initialize(gid); e != nil {
		return PublicationResult{}, e
	}
	current, e := d.current()
	if e != nil {
		return PublicationResult{}, e
	}
	if current == delta.Target {
		return PublicationResult{State: "unchanged", View: current}, nil
	}
	if current != delta.Base {
		return PublicationResult{}, fmt.Errorf("delta predecessor mismatch")
	}
	tmp, e := os.MkdirTemp(filepath.Dir(d.Root), ".delta-")
	if e != nil {
		return PublicationResult{}, e
	}
	defer os.RemoveAll(tmp)
	previous := Store{filepath.Join(d.Root, "snapshots", current)}
	// Pin the source files throughout staging; competing writers may otherwise
	// prune a predecessor. install performs its own CAS after the pin is released.
	lock, e := d.lock(false)
	if e != nil {
		return PublicationResult{}, e
	}
	actual, e := d.current()
	if e != nil || actual != current {
		lock.Close()
		return PublicationResult{}, fmt.Errorf("delta predecessor changed")
	}
	dst := Store{filepath.Join(tmp, "image")}
	e = MaterializeDelta(previous, dst, delta)
	lock.Close()
	if e != nil {
		return PublicationResult{}, e
	}
	result, e := d.Install(dst, current, gid)
	if e != nil {
		return PublicationResult{}, e
	}
	return PublicationResult{State: "installed", View: result.View, CopiedBytes: result.CopiedBytes}, nil
}

func patchCues(old []ReferenceCue, remove []ReferenceCue, insert []CueInsert) ([]ReferenceCue, error) {
	dropped := map[ReferenceCue]bool{}
	for _, c := range remove {
		if dropped[c] {
			return nil, fmt.Errorf("duplicate cue removal")
		}
		dropped[c] = true
	}
	next := make([]ReferenceCue, 0, len(old)+len(insert))
	for _, c := range old {
		if dropped[c] {
			delete(dropped, c)
		} else {
			next = append(next, c)
		}
	}
	if len(dropped) > 0 {
		return nil, fmt.Errorf("missing removed cue")
	}
	last := -1
	for _, c := range insert {
		if c.Position <= last || c.Position > len(next) || c.Position < 0 {
			return nil, fmt.Errorf("invalid cue insertion")
		}
		last = c.Position
		next = append(next, ReferenceCue{})
		copy(next[c.Position+1:], next[c.Position:])
		next[c.Position] = c.Cue
	}
	if old == nil && len(next) == 0 {
		return nil, nil
	}
	return next, nil
}
