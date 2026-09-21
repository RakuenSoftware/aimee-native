package sparse

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"
	"unicode"
)

// ReferenceLookupPolicy is an explicit publisher decision permitting exact
// entity-key lookup of approved public facts. It is not semantic retrieval,
// permission inference from global scope, or a learned model-side router.
// ReferenceCue is explicitly approved routing data. Opaque aliases/metadata
// remain in Aimee; only these signed cue-to-object bindings are delivered.
type ReferenceCue struct {
	Ref       Ref    `json:"ref"`
	Cue       string `json:"cue"`
	Authority string `json:"authority"`
}

type ReferenceLookupPolicy struct {
	Namespace string `json:"namespace"`
	Authority string `json:"authority"`
	Mode      string `json:"mode"`
}

func validateLookupPolicies(policies []ReferenceLookupPolicy) error {
	seen := map[string]bool{}
	for _, p := range policies {
		k := p.Namespace + "/" + p.Authority
		if !namespacePattern.MatchString(p.Namespace) || p.Authority == "" || len(p.Authority) > 256 || p.Mode != "exact-key-v1" || seen[k] {
			return fmt.Errorf("unsupported reference lookup policy")
		}
		seen[k] = true
	}
	return nil
}
func phraseWords(s string) []string {
	// Punctuation inside registry identifiers is significant: pxc and
	// pxc-spvr-ft, or foo-bar and foo_bar, are distinct entity addresses.
	fields := strings.FieldsFunc(strings.ToLower(s), func(r rune) bool {
		return !unicode.IsLetter(r) && !unicode.IsNumber(r) && !strings.ContainsRune("-_/.", r)
	})
	words := make([]string, 0, len(fields))
	for _, field := range fields {
		field = strings.Trim(field, ".") // sentence-final punctuation
		if field != "" {
			words = append(words, field)
		}
	}
	return words
}

type ReferenceLookup struct {
	base        *ReferenceLookup
	view        *View
	grants      map[string]bool
	byAuthority map[string]map[string][]Ref
	maxWords    int
}

// NewReferenceLookup runs after CheckAuthorization. Only independently approved
// canonical key/content fields are indexed. Metadata and aliases are not copied.
func validateReferenceContext(v *View, a Authorization) error {
	_, e := referenceContext(v, a, false)
	return e
}
func NewReferenceLookup(v *View, a Authorization) (*ReferenceLookup, error) {
	return referenceContext(v, a, true)
}
func referenceContext(v *View, a Authorization, build bool) (*ReferenceLookup, error) {
	if err := validateLookupPolicies(a.ReferenceLookups); err != nil {
		return nil, err
	}
	l := &ReferenceLookup{view: v, grants: grantMap(a), byAuthority: map[string]map[string][]Ref{}}
	// Each canonical object is decoded once even when it has many aliases.
	decoded := map[Ref]Record{}
	fingerprints := map[Ref]AuthorizedRecord{}
	read := func(ref Ref) (Record, error) {
		if r, ok := decoded[ref]; ok {
			return r, nil
		}
		loc := v.record(ref.Key())
		if loc == nil {
			return Record{}, fmt.Errorf("reference object unavailable")
		}
		r, e := v.read(loc)
		if e == nil {
			decoded[ref] = r
			fingerprints[ref] = AuthorizeRecord(r)
		}
		return r, e
	}
	for _, p := range a.ReferenceLookups {
		public := false
		for _, layer := range v.Layers {
			if layer.Namespace == p.Namespace && layer.Kind == "general" {
				public = true
			}
		}
		if !public {
			return nil, fmt.Errorf("reference lookup requires an approved general layer")
		}
		if l.byAuthority[p.Authority] == nil {
			l.byAuthority[p.Authority] = map[string][]Ref{}
		}
		for _, approval := range a.Records {
			if approval.Namespace != p.Namespace {
				continue
			}
			loc := v.record(approval.Key())
			if loc == nil {
				return nil, fmt.Errorf("reference object unavailable")
			}
			r, err := read(loc.entry.Ref)
			if err != nil {
				return nil, err
			}
			if r.Ref != approval.Ref || fingerprints[r.Ref] != approval || r.Scope != (Scope{"global", "_global"}) || r.Kind != "fact" || r.Lifecycle != "active" || r.Suppressed || r.Redirect != nil {
				return nil, fmt.Errorf("unsupported reference object")
			}
			words := phraseWords(r.Key)
			if len(words) < 2 || len(words) > 32 {
				return nil, fmt.Errorf("reference key must have 2-32 words")
			}
			if !build {
				continue
			}
			key := strings.Join(words, " ")
			l.byAuthority[p.Authority][key] = append(l.byAuthority[p.Authority][key], r.Ref)
			if len(words) > l.maxWords {
				l.maxWords = len(words)
			}
		}
	}
	approved := map[Ref]AuthorizedRecord{}
	for _, r := range a.Records {
		approved[r.Ref] = r
	}
	for _, cue := range a.ReferenceCues {
		words := phraseWords(cue.Cue)
		approval, ok := approved[cue.Ref]
		if !ok || len(words) < 2 || len(words) > 32 || cue.Authority == "" || len(cue.Cue) > 2048 {
			return nil, fmt.Errorf("invalid or unapproved reference cue")
		}
		loc := v.record(cue.Ref.Key())
		if loc == nil {
			return nil, fmt.Errorf("cue source unavailable")
		}
		r, err := read(loc.entry.Ref)
		if err != nil || r.Ref != cue.Ref || fingerprints[r.Ref] != approval || r.Lifecycle != "active" || r.Suppressed || r.Redirect != nil {
			return nil, fmt.Errorf("invalid cue source")
		}
		if l.byAuthority[cue.Authority] == nil {
			l.byAuthority[cue.Authority] = map[string][]Ref{}
		}
		if !build {
			continue
		}
		key := strings.Join(words, " ")
		refs := l.byAuthority[cue.Authority][key]
		duplicate := false
		for _, ref := range refs {
			if ref == cue.Ref {
				duplicate = true
			}
		}
		if !duplicate {
			l.byAuthority[cue.Authority][key] = append(refs, cue.Ref)
		}
		l.maxWords = max(l.maxWords, len(words))
	}
	return l, nil
}
func (l *ReferenceLookup) Recall(query string, limit int, authority string, now time.Time) RecallResult {
	result := RecallResult{View: l.view.ID, Outcome: "uncovered"}
	if limit < 1 || limit > 32 || len(query) > 16384 {
		return result
	}
	keys := l.byAuthority[authority]
	if len(keys) == 0 && l.base == nil {
		return result
	}
	words := phraseWords(query)
	refs := []Ref{}
	seen := map[Ref]bool{}
	for start := 0; start < len(words); start++ {
		// Longest exact address at this position wins; a longer quantity
		// name must not also activate its shorter prefix quantity.
		maximum := min(l.maxWords, len(words)-start)
		for n := maximum; n >= 2; n-- {
			key := strings.Join(words[start:start+n], " ")
			matches := keys[key]
			if l.base != nil {
				inherited := l.base.byAuthority[authority][key]
				if len(inherited) > 0 {
					matches = append(append([]Ref{}, matches...), inherited...)
				}
			}
			if len(matches) > 1 {
				result.Outcome = "ambiguous"
				return result
			}
			if len(matches) == 1 {
				ref := matches[0]
				if !seen[ref] {
					seen[ref] = true
					refs = append(refs, ref)
				}
				start += n - 1
				break
			}
		}
	}
	if len(refs) == 0 {
		return result
	}
	if len(refs) > limit {
		result.Outcome = "over_budget"
		return result
	}
	facts := []map[string]any{}
	for _, ref := range refs {
		r, err := l.view.Get(ref, l.grants, now)
		if err != nil || r.Ref != ref {
			result.Outcome = "source_unavailable"
			return result
		}
		facts = append(facts, map[string]any{"id": r.ID, "scope": r.Scope, "tier": r.Tier, "kind": r.Kind, "key": r.Key, "content": r.Content, "confidence": r.Confidence})
	}
	result.Response, _ = json.Marshal(map[string]any{"status": "ok", "facts": facts, "windows": []any{}, "active_context_missing": false})
	result.Outcome = "hit"
	return result
}
