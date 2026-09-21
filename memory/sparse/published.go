package sparse

import (
	"encoding/json"
	"fmt"
	"sync"
	"time"
)

// ServingConfig contains compiled routing context, not local access rules.
// Authorization must be resolved BEFORE any bytes enter the recipient's store.
// RecallScopes preserve the keys of existing publisher-produced read contracts.
type ServingConfig struct {
	ReferenceCues    []ReferenceCue          `json:"reference_cues,omitempty"`
	Version          int                     `json:"version"`
	RecallScopes     []string                `json:"recall_scopes,omitempty"`
	ReferenceLookups []ReferenceLookupPolicy `json:"reference_lookups,omitempty"`
}

// PublishedReader consumes a physically filtered snapshot. It holds no signing
// key, grant file, identity verifier or RPC connection. It cannot protect bytes
// that have already been delivered. Publication/withdrawal belongs to Aimee.
type PublishedReader struct {
	parent      *PublishedReader
	lookupOnce  sync.Once
	lookupError error
	View        *View
	Publication string
	lookup      *ReferenceLookup
	context     Authorization
	byID        map[string][]AuthorizedRecord
}

func (s Store) OpenPublished(id string) (*PublishedReader, error) {
	m, e := s.manifest(id)
	if e != nil {
		return nil, e
	}
	if m.Kind == "general" && m.Serving != nil && m.Serving.Version == 1 && m.Previous == "" {
		return s.openGeneral(id)
	}
	return s.openPublishedRaw(id)
}
func (s Store) openPublishedRaw(id string) (_ *PublishedReader, err error) {
	v, err := s.Open(id)
	if err != nil {
		return nil, err
	}
	defer func() {
		if err != nil {
			v.Close()
		}
	}()
	tip := v.Layers[len(v.Layers)-1]
	if tip.Serving == nil || (tip.Serving.Version != 1 && tip.Serving.Version != 2) || tip.Authorization == "" {
		return nil, fmt.Errorf("expected a compiled recipient snapshot")
	}
	// Integrity validation, not authorization. Never accept a raw source graph
	// accidentally as a delivery snapshot. Only the publisher can ensure that
	// the directory was populated with appropriate data in the first place.
	for _, m := range v.Layers {
		if m.Previous != "" || m.Source != "authorized knowledge snapshot" || (tip.Serving.Version == 1 && m.Authorization != tip.Authorization) {
			return nil, fmt.Errorf("expected a compiled recipient snapshot")
		}
	}
	// openOverlay has already checked the immutable base objects.
	if err = v.verifyLocal(); err != nil {
		return nil, err
	}
	p := &PublishedReader{View: v, Publication: tip.Authorization, byID: map[string][]AuthorizedRecord{}}
	p.context.Grants = tip.Serving.RecallScopes
	if v.base != nil {
		// openOverlay holds a lease to this cached base for the view lifetime.
		p.parent = v.basePublished
		if p.parent == nil || p.parent.View != v.base {
			return nil, fmt.Errorf("base reader lease unavailable")
		}
		p.context.Grants = append(append([]string{}, p.parent.context.Grants...), tip.Serving.RecallScopes...)
	}
	p.context.ReferenceLookups = tip.Serving.ReferenceLookups
	p.context.ReferenceCues = tip.Serving.ReferenceCues
	for _, loc := range v.records {
		r, e := v.read(loc)
		if e != nil {
			return nil, e
		}
		entry := AuthorizeRecord(r) // canonical fingerprint, computed once
		p.context.Records = append(p.context.Records, entry)
		p.byID[r.ID] = append(p.byID[r.ID], entry)
	}
	// Validate routing once without building the phrase index on publisher paths.
	if err = validateReferenceContext(v, p.context); err != nil {
		return nil, err
	}
	return p, nil
}

func (p *PublishedReader) ensureLookup() error {
	p.lookupOnce.Do(func() {
		if p.parent != nil {
			if p.lookupError = p.parent.ensureLookup(); p.lookupError != nil {
				return
			}
		}
		p.lookup, p.lookupError = NewReferenceLookup(p.View, p.context)
		if p.lookupError == nil && p.parent != nil {
			p.lookup.base = p.parent.lookup
			p.lookup.maxWords = max(p.lookup.maxWords, p.parent.lookup.maxWords)
		}
	})
	return p.lookupError
}
func (p *PublishedReader) approvals(id string) []AuthorizedRecord {
	out := p.byID[id]
	if p.parent != nil {
		out = append(append([]AuthorizedRecord{}, out...), p.parent.approvals(id)...)
	}
	return out
}
func (p *PublishedReader) Close() { p.View.Close() }

// Recall preserves compiled retrieval and temporal semantics. All stored rows
// have already been admitted by the publisher. It never reauthorizes a read.
func (p *PublishedReader) Recall(query string, limit int, authority string, now time.Time) (RecallResult, error) {
	r := p.View.Recall(query, limit, authority, grantMap(p.context), now)
	if r.Outcome == "uncovered" {
		if err := p.ensureLookup(); err != nil {
			return r, err
		}
		r = p.lookup.Recall(query, limit, authority, now)
	}
	if r.Outcome != "hit" {
		return r, nil
	}
	var body struct {
		Facts []map[string]json.RawMessage `json:"facts"`
	}
	if err := json.Unmarshal(r.Response, &body); err != nil {
		return r, err
	}
	// Resolve only returned IDs, avoiding a corpus scan and preserving collision
	// detection across namespaces. This binds payloads to canonical identities.
	context := p.context
	context.Records = nil
	seen := map[Ref]bool{}
	for _, f := range body.Facts {
		var id string
		if json.Unmarshal(f["id"], &id) != nil {
			id = string(f["id"])
		}
		for _, entry := range p.approvals(id) {
			if !seen[entry.Ref] {
				context.Records = append(context.Records, entry)
				seen[entry.Ref] = true
			}
		}
	}
	refs, err := p.View.ResolveResponse(r.Response, context, now)
	if err != nil {
		return r, err
	}
	var response map[string]any
	if err := json.Unmarshal(r.Response, &response); err != nil {
		return r, err
	}
	for i, f := range response["facts"].([]any) {
		f.(map[string]any)["memory_ref"] = refs[i]
		canonical, e := p.View.Get(refs[i], grantMap(p.context), now)
		if e != nil {
			return r, e
		}
		f.(map[string]any)["memory_hash"] = AuthorizeRecord(canonical).SHA256
	}
	r.Response, err = json.Marshal(response)
	return r, err
}

// RetentionProof binds a disposable encoding to an exact current canonical object.
// The local directory has already been authorized; this is cache coherency only.
type RetentionProof struct {
	Ref  Ref    `json:"memory_ref"`
	Hash string `json:"memory_hash"`
}

func (p *PublishedReader) Retain(proofs []RetentionProof, now time.Time) []bool {
	result := make([]bool, len(proofs))
	for i, proof := range proofs {
		if !digestPattern.MatchString(proof.Hash) {
			continue
		}
		r, e := p.View.Get(proof.Ref, grantMap(p.context), now)
		result[i] = e == nil && r.Ref == proof.Ref && AuthorizeRecord(r).SHA256 == proof.Hash
	}
	return result
}

// RestrictRemote narrows an already authenticated Aimee read to the records
// released into this snapshot. It grants no upstream access by itself.
func (p *PublishedReader) remoteContext(namespace string) Authorization {
	a := Authorization{Grants: p.context.Grants}
	if p.parent != nil && namespace != p.View.Layers[len(p.View.Layers)-1].Namespace {
		a.Records = p.parent.remoteContext(namespace).Records
	}
	for _, r := range p.context.Records {
		if r.Namespace == namespace {
			a.Records = append(a.Records, r)
		}
	}
	return a
}
func (p *PublishedReader) RestrictRemote(namespace string) (SearchRestriction, error) {
	return RestrictSearch(p.remoteContext(namespace), namespace)
}
func (p *PublishedReader) ResolveRemote(raw json.RawMessage, now time.Time) ([]Ref, error) {
	var body struct {
		Restriction *SearchRestriction `json:"restriction"`
	}
	if json.Unmarshal(raw, &body) != nil || body.Restriction.Validate() != nil {
		return nil, fmt.Errorf("restricted upstream receipt required")
	}
	return p.View.ResolveResponse(raw, p.remoteContext(body.Restriction.Namespace), now)
}
