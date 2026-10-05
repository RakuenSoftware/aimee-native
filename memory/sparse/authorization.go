package sparse

import (
	"bytes"
	"crypto/ed25519"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"time"
)

// Authorization is an Aimee control-plane decision, never model-supplied scope.
// Each approval covers only the minimal serving projection of a canonical object.
// Scope labels alone do not authorize export, including "global" labels.
type AuthorizedRecord struct {
	Ref
	SHA256 string `json:"sha256"`
}
type Authorization struct {
	CandidateRoutes  []CandidateRoute        `json:"candidate_routes,omitempty"`
	ReferenceCues    []ReferenceCue          `json:"reference_cues,omitempty"`
	ReferenceLookups []ReferenceLookupPolicy `json:"reference_lookups,omitempty"`
	Version          int                     `json:"version"`
	ID               string                  `json:"id"`
	Subject          string                  `json:"subject"`
	PolicyEpoch      string                  `json:"policy_epoch"`
	SourceView       string                  `json:"source_view"`
	Active           bool                    `json:"active"`
	ValidUntil       string                  `json:"valid_until"`
	Grants           []string                `json:"grants"`
	Records          []AuthorizedRecord      `json:"records"`
	ReadDigests      []string                `json:"read_digests"`
}
type SignedAuthorization struct {
	Grant     json.RawMessage `json:"grant"`
	Signature []byte          `json:"signature"`
}

func SignAuthorization(a Authorization, key ed25519.PrivateKey) (SignedAuthorization, error) {
	if len(key) != ed25519.PrivateKeySize {
		return SignedAuthorization{}, fmt.Errorf("invalid authorization signing key")
	}
	raw, err := json.Marshal(a)
	if err != nil {
		return SignedAuthorization{}, err
	}
	return SignedAuthorization{raw, ed25519.Sign(key, raw)}, nil
}
func VerifyAuthorization(s SignedAuthorization, key ed25519.PublicKey, subject, epoch string, now time.Time) (Authorization, error) {
	var a Authorization
	if len(key) != ed25519.PublicKeySize || !ed25519.Verify(key, s.Grant, s.Signature) {
		return a, fmt.Errorf("authorization signature rejected")
	}
	if json.Unmarshal(s.Grant, &a) != nil || a.Version != 1 || !a.Active || a.ID == "" || subject == "" || epoch == "" || a.Subject != subject || a.PolicyEpoch != epoch || !digestPattern.MatchString(a.SourceView) {
		return a, fmt.Errorf("authorization binding rejected")
	}
	until, err := time.Parse(time.RFC3339Nano, a.ValidUntil)
	if err != nil || !now.Before(until) {
		return a, fmt.Errorf("authorization expired")
	}
	if err := validateLookupPolicies(a.ReferenceLookups); err != nil {
		return a, err
	}
	seen := map[string]bool{}
	for _, r := range a.Records {
		if validateRef(r.Ref) != nil || !digestPattern.MatchString(r.SHA256) || seen[r.Key()] {
			return a, fmt.Errorf("invalid record authorization")
		}
		seen[r.Key()] = true
	}
	return a, nil
}
func (s SignedAuthorization) Digest() string { return digest(s.Grant) }
func ReadDigest(c ReadContract) string       { b, _ := json.Marshal(c); return digest(b) }

// ServingRecord deliberately excludes opaque source metadata, aliases, edges,
// redirects and evidence. They need separate field-level Aimee authorization.
// Keep the full canonical object in Aimee; do not overwrite it with this form.
func ServingRecord(r Record) Record {
	r.Metadata = nil
	r.Aliases = nil
	r.Edges = nil
	r.Redirect = nil
	return r
}
func AuthorizeRecord(r Record) AuthorizedRecord {
	b, _ := json.Marshal(ServingRecord(r))
	return AuthorizedRecord{r.Ref, digest(b)}
}
func grantMap(a Authorization) map[string]bool {
	g := map[string]bool{}
	for _, x := range a.Grants {
		g[x] = true
	}
	return g
}

// CompileAuthorized builds a fresh audience-only directory. No source objects,
// ancestry, metadata or old versions are copied. The destination must not exist:
// reusing a directory could retain previously authorized or foreign bytes.
func (s Store) CompileAuthorized(dst Store, signed SignedAuthorization, key ed25519.PublicKey, subject, epoch string, now time.Time) (id string, err error) {
	a, err := VerifyAuthorization(signed, key, subject, epoch, now)
	if err != nil {
		return "", err
	}
	v, err := s.Open(a.SourceView)
	if err != nil {
		return "", err
	}
	defer v.Close()
	records := map[string][]Record{}
	allowed := map[Ref]bool{}
	for _, approval := range a.Records {
		r, e := v.Get(approval.Ref, grantMap(a), now)
		if e != nil || r.Ref != approval.Ref || AuthorizeRecord(r) != approval {
			return "", fmt.Errorf("approved source unavailable or changed")
		}
		if r.Redirect != nil {
			return "", fmt.Errorf("redirects need authority resolution")
		}
		records[r.Namespace] = append(records[r.Namespace], ServingRecord(r))
		allowed[r.Ref] = true
	}
	reads := []ReadContract{}
	for _, wanted := range a.ReadDigests {
		found := false
		for _, c := range v.reads {
			if ReadDigest(c) != wanted {
				continue
			}
			found = true
			if readKey(c.Query, c.Limit, c.Authority, c.Grants) != readKey(c.Query, c.Limit, c.Authority, a.Grants) {
				return "", fmt.Errorf("read grant mismatch")
			}
			for _, ref := range c.Dependencies {
				if !allowed[ref] {
					return "", fmt.Errorf("read includes unauthorized source")
				}
			}
			if v.Recall(c.Query, c.Limit, c.Authority, grantMap(a), now).Outcome != "hit" {
				return "", fmt.Errorf("read decision unavailable")
			}
			reads = append(reads, c)
		}
		if !found {
			return "", fmt.Errorf("read decision unavailable")
		}
	}
	if err = validateCandidateRoutes(v, a.CandidateRoutes, a.Records, grantMap(a), now); err != nil {
		return "", err
	}
	if _, err = NewReferenceLookup(v, a); err != nil {
		return "", err
	}
	sort.Slice(reads, func(i, j int) bool { return ReadDigest(reads[i]) < ReadDigest(reads[j]) })
	if err = os.Mkdir(dst.Root, 0700); err != nil {
		return "", fmt.Errorf("authorized destination must be new: %w", err)
	}
	defer func() {
		if err != nil {
			os.RemoveAll(dst.Root)
		}
	}()
	layers := []Manifest{}
	for _, m := range v.Layers {
		if len(records[m.Namespace]) > 0 || m.Kind == "general" {
			layers = append(layers, m)
		}
	}
	for i, m := range layers {
		ns := m.Namespace
		if m.Kind == "general" && len(records[ns]) == 0 {
			ns = "authorized-empty"
		}
		c := ChangeSet{Namespace: ns, Kind: m.Kind, Generation: 1, Upstream: id, Records: records[m.Namespace], Source: "authorized knowledge snapshot", Coverage: []string{"authorized_canonical_fields"}, Authorization: signed.Digest()}
		if i == len(layers)-1 {
			c.ReadContracts = reads
			c.Serving = &ServingConfig{Version: 1, RecallScopes: a.Grants, ReferenceLookups: a.ReferenceLookups, ReferenceCues: a.ReferenceCues, CandidateRoutes: a.CandidateRoutes}
		}
		id, err = dst.Build(c)
		if err != nil {
			return "", err
		}
	}
	if err = dst.Publish(id, ""); err != nil {
		return "", err
	}
	// Keep grants and signing material on the publisher. Serving metadata is
	// already committed into the tip manifest; the recipient needs no grant file.
	return id, nil
}

// CheckAuthorization validates an already-materialized serving view, including
// every record, against an independently trusted authorization decision.
func (v *View) CheckAuthorization(s SignedAuthorization, key ed25519.PublicKey, subject, epoch string, now time.Time) error {
	a, err := VerifyAuthorization(s, key, subject, epoch, now)
	if err != nil {
		return err
	}
	expectedServing, _ := json.Marshal(ServingConfig{Version: 1, RecallScopes: a.Grants, ReferenceLookups: a.ReferenceLookups, ReferenceCues: a.ReferenceCues, CandidateRoutes: a.CandidateRoutes})
	for i, m := range v.Layers {
		if i == len(v.Layers)-1 {
			got, _ := json.Marshal(m.Serving)
			if !bytes.Equal(got, expectedServing) {
				return fmt.Errorf("unauthorized serving configuration")
			}
		} else if m.Serving != nil {
			return fmt.Errorf("unexpected intermediate serving configuration")
		}
	}
	approved := map[Ref]string{}
	for _, r := range a.Records {
		approved[r.Ref] = r.SHA256
	}
	if v.recordCount() != len(approved) {
		return fmt.Errorf("image record set differs from authorization")
	}
	for _, m := range v.Layers {
		if m.Authorization != s.Digest() || m.Previous != "" || m.Source != "authorized knowledge snapshot" || len(m.Delete) > 0 || len(m.Suppressions) > 0 {
			return fmt.Errorf("image is not an authorized snapshot")
		}
	}
	for _, loc := range v.allRecords() {
		r, e := v.read(loc)
		if e != nil {
			return e
		}
		b, _ := json.Marshal(r)
		if approved[r.Ref] != digest(b) || len(r.Metadata) > 0 || len(r.Aliases) > 0 || len(r.Edges) > 0 || r.Redirect != nil {
			return fmt.Errorf("unauthorized image payload")
		}
	}
	permitted := map[string]bool{}
	for _, h := range a.ReadDigests {
		permitted[h] = true
	}
	for _, c := range v.reads {
		if !permitted[ReadDigest(c)] {
			return fmt.Errorf("unauthorized read decision")
		}
	}
	// Reconstruct each physical object, not just visible rows. This rejects
	// hidden bytes, stale records, extra index terms and unknown JSON fields.
	upstream := ""
	physicalObjects := map[string]bool{}
	for _, m := range v.Layers {
		locations := []*location{}
		for _, loc := range v.allRecords() {
			if loc.entry.Namespace == m.Namespace {
				locations = append(locations, loc)
			}
		}
		sort.Slice(locations, func(i, j int) bool { return locations[i].entry.Offset < locations[j].entry.Offset })
		var data bytes.Buffer
		idx := Index{Postings: map[string][]int{}}
		for _, loc := range locations {
			r, e := v.read(loc)
			if e != nil {
				return e
			}
			raw, _ := json.Marshal(r)
			raw = append(raw, '\n')
			expected := Entry{Ref: r.Ref, Offset: int64(data.Len()), Length: len(raw), SHA256: digest(raw), Scope: r.Scope, Lifecycle: r.Lifecycle, Suppressed: r.Suppressed, Confidence: r.Confidence, ValidFrom: r.ValidFrom, ValidUntil: r.ValidUntil}
			idx.Entries = append(idx.Entries, expected)
			for _, term := range Terms(r.Key + " " + r.Content) {
				idx.Postings[term] = append(idx.Postings[term], len(idx.Entries)-1)
			}
			data.Write(raw)
		}
		rawIndex, _ := json.Marshal(idx)
		if m.Data != digest(data.Bytes()) || m.Index != digest(rawIndex) || m.Upstream != upstream || m.Generation != 1 || len(m.Coverage) != 1 || m.Coverage[0] != "authorized_canonical_fields" {
			return fmt.Errorf("unauthorized physical image contents")
		}
		rawManifest, _ := json.Marshal(m)
		upstream = digest(rawManifest)
		physicalObjects[upstream] = true
		physicalObjects[m.Data] = true
		physicalObjects[m.Index] = true
	}
	if upstream != v.ID {
		return fmt.Errorf("noncanonical authorization manifest")
	}
	if len(v.files) == 0 {
		return fmt.Errorf("authorized image has no data object")
	}
	objectDir := filepath.Dir(v.files[0].Name())
	entries, e := os.ReadDir(objectDir)
	if e != nil {
		return e
	}
	for _, entry := range entries {
		if !physicalObjects[entry.Name()] || !entry.Type().IsRegular() {
			return fmt.Errorf("unauthorized extra image object")
		}
	}
	return v.Verify()
}

// AuthorizeResponse is a conservative egress guard for fallback connections
// without Aimee-issued delegated credentials. It never returns a partial answer.
// Rich evidence/episode schemas need their own authoritative release decisions.
func (v *View) AuthorizeResponse(raw json.RawMessage, a Authorization, now time.Time) error {
	_, err := v.ResolveResponse(raw, a, now)
	return err
}

// ResolveResponse binds released facts to canonical namespace/ID/revision.
// Ambiguous legacy IDs fail closed instead of merging distinct knowledge objects.
func (v *View) ResolveResponse(raw json.RawMessage, a Authorization, now time.Time) ([]Ref, error) {
	var body map[string]json.RawMessage
	if json.Unmarshal(raw, &body) != nil || body == nil {
		return nil, fmt.Errorf("unsupported authority response")
	}
	for k := range body {
		if k != "status" && k != "facts" && k != "windows" && k != "active_context_missing" && k != "restriction" {
			return nil, fmt.Errorf("unsupported authority response fields")
		}
	}
	if value, ok := body["status"]; ok && string(value) != `"ok"` {
		return nil, fmt.Errorf("authority did not return success")
	}
	var missing bool
	if value, ok := body["active_context_missing"]; ok && (json.Unmarshal(value, &missing) != nil || missing) {
		return nil, fmt.Errorf("authority context incomplete")
	}
	var windows []json.RawMessage
	if value, ok := body["windows"]; ok && (json.Unmarshal(value, &windows) != nil || len(windows) > 0) {
		return nil, fmt.Errorf("episode authorization unsupported")
	}
	restricted := false
	restrictedNamespace := ""
	if receipt, ok := body["restriction"]; ok {
		if err := validateRestrictionReceipt(receipt, a); err != nil {
			return nil, err
		}
		restricted = true
		var receiptBinding SearchRestriction
		_ = json.Unmarshal(receipt, &receiptBinding)
		restrictedNamespace = receiptBinding.Namespace
	}
	var facts []map[string]json.RawMessage
	if value, ok := body["facts"]; !ok || json.Unmarshal(value, &facts) != nil || facts == nil || (len(facts) == 0 && !restricted) {
		// Legacy empty and non-releasable results share an unavailable response.
		// Only an acknowledged restricted read can report an authorized miss.
		return nil, fmt.Errorf("no releasable facts")
	}
	refs := make([]Ref, 0, len(facts))
	for _, f := range facts {
		for k := range f {
			if k != "id" && k != "scope" && k != "tier" && k != "kind" && k != "key" && k != "content" && k != "confidence" {
				return nil, fmt.Errorf("fact field authorization unsupported")
			}
		}
		var id, content string
		if json.Unmarshal(f["id"], &id) != nil {
			id = string(f["id"])
		}
		if json.Unmarshal(f["content"], &content) != nil {
			return nil, fmt.Errorf("invalid fact content")
		}
		var matches []Ref
		for _, ref := range a.Records {
			if ref.ID != id || (restricted && ref.Namespace != restrictedNamespace) {
				continue
			}
			r, err := v.Get(ref.Ref, grantMap(a), now)
			if err != nil || r.Ref != ref.Ref || r.Content != content {
				continue
			}
			fields := map[string]any{"scope": r.Scope, "tier": r.Tier, "kind": r.Kind, "key": r.Key, "confidence": r.Confidence}
			valid := true
			for k, want := range fields {
				if got, ok := f[k]; ok {
					b, _ := json.Marshal(want)
					var x, y any
					_ = json.Unmarshal(got, &x)
					_ = json.Unmarshal(b, &y)
					left, _ := json.Marshal(x)
					right, _ := json.Marshal(y)
					if !bytes.Equal(left, right) {
						valid = false
					}
				}
			}
			if valid {
				matches = append(matches, r.Ref)
			}
		}
		if len(matches) != 1 {
			return nil, fmt.Errorf("authority response exceeds authorization or has ambiguous identity")
		}
		refs = append(refs, matches[0])
	}
	return refs, nil
}
