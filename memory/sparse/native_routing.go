package sparse

// Candidate routes are publisher-approved complete record bundles, not grants.
// They are immutable tip-manifest routing data; no inherited route can survive a
// new publication unless its publisher explicitly republishes it.
import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"
)

type CandidateRoute struct {
	Partition string   `json:"partition"`
	Authority string   `json:"authority"`
	Cues      []string `json:"cues"`
	Records   []Ref    `json:"records"`
}
type NativeAddress struct {
	Schema         int      `json:"schema"`
	View           string   `json:"view"`
	Representation string   `json:"representation"`
	Step           uint64   `json:"step"`
	Partitions     []string `json:"partitions,omitempty"`
}
type RoutedRecall struct {
	RecallResult
	CandidatePartitions int   `json:"candidate_partitions"`
	CandidateRecords    int   `json:"candidate_records"`
	Fallback            bool  `json:"fallback"`
	RoutingMicros       int64 `json:"routing_micros"`
}
type candidateIndex struct {
	cues     map[string]map[string][]int
	routes   []CandidateRoute
	maxWords int
}

func validateCandidateRoutes(v *View, routes []CandidateRoute, approvals []AuthorizedRecord, grants map[string]bool, now time.Time) error {
	allowed := map[Ref]AuthorizedRecord{}
	for _, a := range approvals {
		allowed[a.Ref] = a
	}
	seen := map[string]bool{}
	for _, route := range routes {
		key := route.Authority + "\x00" + route.Partition
		if route.Authority == "" || len(route.Authority) > 256 || route.Partition == "" || len(route.Partition) > 256 || seen[key] ||
			len(route.Cues) < 1 || len(route.Cues) > 32 || len(route.Records) < 1 || len(route.Records) > 32 {
			return fmt.Errorf("invalid candidate route")
		}
		seen[key] = true
		refs := map[Ref]bool{}
		for _, ref := range route.Records {
			approval, ok := allowed[ref]
			if !ok || refs[ref] {
				return fmt.Errorf("candidate route includes unavailable or unapproved revision")
			}
			if !now.IsZero() {
				r, e := v.Get(ref, grants, now)
				if e != nil || r.Ref != ref || AuthorizeRecord(r) != approval {
					return fmt.Errorf("candidate route includes unavailable or unapproved revision")
				}
			}
			refs[ref] = true
		}
		cues := map[string]bool{}
		for _, cue := range route.Cues {
			words := phraseWords(cue)
			canonical := strings.Join(words, " ")
			if len(cue) > 2048 || len(words) < 1 || len(words) > 32 || cues[canonical] {
				return fmt.Errorf("invalid candidate cue")
			}
			cues[canonical] = true
		}
	}
	return nil
}
func (p *PublishedReader) ensureRoutes(now time.Time) error {
	p.routesOnce.Do(func() {
		routes := p.View.Layers[len(p.View.Layers)-1].Serving.CandidateRoutes
		approvals := []AuthorizedRecord{}
		for _, route := range routes {
			for _, ref := range route.Records {
				approvals = append(approvals, p.approvals(ref.ID)...)
			}
		}
		p.routesError = validateCandidateRoutes(p.View, routes, approvals, grantMap(p.context), time.Time{})
		if p.routesError != nil {
			return
		}
		idx := &candidateIndex{routes: routes, cues: map[string]map[string][]int{}}
		for i, route := range routes {
			if idx.cues[route.Authority] == nil {
				idx.cues[route.Authority] = map[string][]int{}
			}
			for _, cue := range route.Cues {
				words := phraseWords(cue)
				key := strings.Join(words, " ")
				idx.cues[route.Authority][key] = append(idx.cues[route.Authority][key], i)
				idx.maxWords = max(idx.maxWords, len(words))
			}
		}
		p.routes = idx
	})
	return p.routesError
}

// RouteNative first bounds partitions/candidates, then resolves exact current
// canonical records. Hints only narrow matching routes. A rejected/stale binding
// is terminal; a routing miss gets at most one existing bounded local fallback.
func (p *PublishedReader) RouteNative(address NativeAddress, query string, limit int, authority string, now time.Time) (result RoutedRecall, err error) {
	started := time.Now()
	defer func() { result.RoutingMicros = time.Since(started).Microseconds() }()
	result.RecallResult = RecallResult{View: p.View.ID, Outcome: "uncovered"}
	if address.Schema != 1 || address.View != p.View.ID || len(query) > 16384 || strings.TrimSpace(query) == "" || limit < 1 || limit > 32 ||
		len(address.Partitions) > 32 || (address.Representation != "text-query-v1" && address.Representation != "attention-token-spans-v1") {
		return result, fmt.Errorf("invalid native address binding or budget")
	}
	if err = p.ensureRoutes(now); err != nil {
		return result, err
	}
	hints := map[string]bool{}
	for _, hint := range address.Partitions {
		if hint == "" || len(hint) > 256 || hints[hint] {
			return result, fmt.Errorf("invalid candidate hint")
		}
		hints[hint] = true
	}
	words := phraseWords(query)
	matches := map[int]bool{}
	refs := []Ref{}
	seen := map[Ref]bool{}
	for start := 0; start < len(words); start++ {
		for n := min(p.routes.maxWords, len(words)-start); n >= 1; n-- {
			routes := p.routes.cues[authority][strings.Join(words[start:start+n], " ")]
			if len(routes) > 1 {
				result.Outcome = "ambiguous"
				return result, nil
			}
			if len(routes) == 1 {
				i := routes[0]
				if len(hints) == 0 || hints[p.routes.routes[i].Partition] {
					matches[i] = true
				}
				start += n - 1
				break
			}
		}
	}
	result.CandidatePartitions = len(matches)
	if len(matches) == 0 {
		result.Fallback = true
		result.RecallResult, err = p.recallLegacy(query, limit, authority, now)
		return result, err
	}
	if len(matches) > limit {
		result.Outcome = "over_budget"
		return result, nil
	}
	// Preserve publisher order, independent of map iteration or hint order.
	indices := make([]int, 0, len(matches))
	for i := range matches {
		indices = append(indices, i)
	}
	sort.Ints(indices)
	for _, i := range indices {
		route := p.routes.routes[i]
		for _, ref := range route.Records {
			if !seen[ref] {
				seen[ref] = true
				refs = append(refs, ref)
			}
			if len(refs) > limit {
				result.CandidateRecords = len(refs)
				result.Outcome = "over_budget"
				return result, nil
			}
		}
	}
	result.CandidateRecords = len(refs)
	facts := []map[string]any{}
	for _, ref := range refs {
		record, e := p.View.Get(ref, grantMap(p.context), now)
		if e != nil || record.Ref != ref {
			result.Outcome = "source_unavailable"
			return result, nil
		}
		facts = append(facts, map[string]any{"id": record.ID, "scope": record.Scope, "tier": record.Tier, "kind": record.Kind,
			"key": record.Key, "content": record.Content, "confidence": record.Confidence,
			"memory_ref": ref, "memory_hash": AuthorizeRecord(record).SHA256})
	}
	result.Response, err = json.Marshal(map[string]any{"status": "ok", "facts": facts, "windows": []any{}, "active_context_missing": false})
	result.Outcome = "hit"
	return result, err
}
