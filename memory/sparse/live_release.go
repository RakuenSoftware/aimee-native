package sparse

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"time"
)

// CompileReleased overlays the memory module's explicitly released current rows
// on an exact approved public base. The caller must obtain a canonical policy
// decision before calling. No grant/signing material enters the recipient image.
func (s Store) CompileReleased(base Store, baseID, binding, namespace, authority string, records []Record, cues []ReferenceCue, now time.Time) (string, error) {
	return s.CompileReleasedRoutes(base, baseID, binding, namespace, authority, records, cues, nil, now)
}

// CompileReleasedRoutes accepts routing metadata from the trusted publisher.
// Every target must be a current released row or a physically approved base row.
// Routes are explicitly republished; they are not inherited from older overlays.
func (s Store) CompileReleasedRoutes(base Store, baseID, binding, namespace, authority string, records []Record, cues []ReferenceCue, routes []CandidateRoute, now time.Time) (string, error) {
	p, e := base.OpenPublished(baseID)
	if e != nil {
		return "", e
	}
	defer p.Close()
	if len(p.View.Layers) != 1 || p.View.Layers[0].Kind != "general" {
		return "", fmt.Errorf("exact general base required")
	}
	if e = os.MkdirAll(filepath.Join(s.Root, "objects"), 0700); e != nil {
		return "", e
	}
	m := p.View.Layers[0]
	for _, h := range []string{baseID, m.Data, m.Index} {
		src, _ := base.object(h)
		dst, _ := s.object(h)
		if e = os.Link(src, dst); e != nil && !os.IsExist(e) {
			if _, e = copyDeliveryObject(src, dst, h); e != nil {
				return "", e
			}
		}
	}
	serving := ServingConfig{Version: 2, RecallScopes: []string{"user:_user"}, ReferenceCues: append([]ReferenceCue{}, cues...), CandidateRoutes: append([]CandidateRoute{}, routes...)}
	sort.Slice(records, func(i, j int) bool { return records[i].ID < records[j].ID })
	active := map[Ref]bool{}
	for i, r := range records {
		if r.Namespace != namespace || r.Lifecycle != "active" || r.Suppressed || r.Redirect != nil {
			return "", fmt.Errorf("unservable released record")
		}
		if r.ValidFrom != "" {
			t, e := time.Parse(time.RFC3339Nano, r.ValidFrom)
			if e != nil || now.Before(t) {
				return "", fmt.Errorf("unservable temporal record")
			}
		}
		if r.ValidUntil != "" {
			t, e := time.Parse(time.RFC3339Nano, r.ValidUntil)
			if e != nil || !now.Before(t) {
				return "", fmt.Errorf("unservable temporal record")
			}
		}
		records[i] = ServingRecord(r)
		active[r.Ref] = true
	}
	approvals := append([]AuthorizedRecord{}, p.context.Records...)
	for _, r := range records {
		approvals = append(approvals, AuthorizeRecord(r))
	}
	if e = validateCandidateRoutes(nil, routes, approvals, nil, time.Time{}); e != nil {
		return "", e
	}
	for _, c := range cues {
		if !active[c.Ref] {
			return "", fmt.Errorf("cue targets unreleased record")
		}
	}
	return s.Build(ChangeSet{Namespace: namespace, Kind: "server", Generation: 1, Upstream: baseID, Records: records, Source: "authorized knowledge snapshot", Coverage: []string{"released_memory_rows"}, Authorization: binding, Serving: &serving})
}
