// Package sparse implements disposable local serving images owned by Aimee.
// Images preserve authoritative identities; they are not an authoritative store.
package sparse

import (
	"encoding/json"
	"fmt"
	"math"
	"regexp"
	"strings"
	"time"
	"unicode"
)

const FormatVersion = 1

type Ref struct {
	Namespace string `json:"namespace"`
	ID        string `json:"id"`
	Revision  string `json:"revision"`
}

func (r Ref) Key() string { return r.Namespace + ":" + r.ID }

type Scope struct {
	Type  string `json:"type"`
	Value string `json:"value"`
}

func (s Scope) Key() string { return s.Type + ":" + s.Value }

type Edge struct {
	Relation string `json:"relation"`
	Target   Ref    `json:"target"`
}

// Record retains its authoritative payload and lineage. Metadata is opaque to
// this first codec; it must not be mistaken for implemented policy or retrieval.
type Record struct {
	Ref
	Scope      Scope           `json:"scope"`
	Key        string          `json:"key"`
	Content    string          `json:"content"`
	Kind       string          `json:"kind"`
	Tier       string          `json:"tier"`
	Confidence float64         `json:"confidence"`
	Lifecycle  string          `json:"lifecycle"`
	Suppressed bool            `json:"suppressed,omitempty"`
	ValidFrom  string          `json:"valid_from,omitempty"`
	ValidUntil string          `json:"valid_until,omitempty"`
	Aliases    []string        `json:"aliases,omitempty"`
	Edges      []Edge          `json:"edges,omitempty"`
	Redirect   *Ref            `json:"redirect,omitempty"`
	Metadata   json.RawMessage `json:"metadata,omitempty"`
}

// Suppression is an explicit upstream resolution from Aimee, never an inferred
// last-layer-wins rule. Revision pinning detects unreconciled upstream changes.
type Suppression struct {
	Target  Ref    `json:"target"`
	Reason  string `json:"reason"`
	Scope   Scope  `json:"scope"`
	Release bool   `json:"release,omitempty"`
}

// ChangeSet is one authoritative source's snapshot (no Previous) or delta.
// Upstream is a manifest digest, not a mutable path or a latest-version alias.
type ChangeSet struct {
	Serving       *ServingConfig `json:"serving,omitempty"`
	Authorization string         `json:"authorization,omitempty"`
	ReadContracts []ReadContract `json:"read_contracts,omitempty"`
	Namespace     string         `json:"namespace"`
	Kind          string         `json:"kind"` // general, kb, server
	Generation    uint64         `json:"generation"`
	Previous      string         `json:"previous,omitempty"`
	Upstream      string         `json:"upstream,omitempty"`
	Records       []Record       `json:"records"`
	Delete        []Ref          `json:"delete,omitempty"`
	Suppressions  []Suppression  `json:"suppressions,omitempty"`
	Source        string         `json:"source"`
	Coverage      []string       `json:"coverage"`
}

type Entry struct {
	Ref
	Offset     int64   `json:"offset"`
	Length     int     `json:"length"`
	SHA256     string  `json:"sha256"`
	Scope      Scope   `json:"scope"`
	Lifecycle  string  `json:"lifecycle"`
	Suppressed bool    `json:"suppressed,omitempty"`
	Confidence float64 `json:"confidence"`
	ValidFrom  string  `json:"valid_from,omitempty"`
	ValidUntil string  `json:"valid_until,omitempty"`
	Redirect   *Ref    `json:"redirect,omitempty"`
	Edges      []Edge  `json:"edges,omitempty"`
}
type Index struct {
	Entries  []Entry          `json:"entries"`
	Postings map[string][]int `json:"postings"`
}
type Manifest struct {
	Serving       *ServingConfig `json:"serving,omitempty"`
	Authorization string         `json:"authorization,omitempty"`
	ReadContracts []ReadContract `json:"read_contracts,omitempty"`
	Format        int            `json:"format"`
	Namespace     string         `json:"namespace"`
	Kind          string         `json:"kind"`
	Generation    uint64         `json:"generation"`
	Previous      string         `json:"previous,omitempty"`
	Upstream      string         `json:"upstream,omitempty"`
	Data          string         `json:"data"`
	Index         string         `json:"index"`
	Delete        []Ref          `json:"delete,omitempty"`
	Suppressions  []Suppression  `json:"suppressions,omitempty"`
	Source        string         `json:"source"`
	Coverage      []string       `json:"coverage"`
}

var namespacePattern = regexp.MustCompile(`^[A-Za-z0-9_.-]+$`)
var digestPattern = regexp.MustCompile(`^[a-f0-9]{64}$`)

func validateRef(r Ref) error {
	if !namespacePattern.MatchString(r.Namespace) || strings.TrimSpace(r.ID) == "" || strings.TrimSpace(r.Revision) == "" {
		return fmt.Errorf("invalid record reference: %q", r.Key())
	}
	return nil
}
func validateRecord(r Record, namespace, kind string) error {
	if err := validateRef(r.Ref); err != nil {
		return err
	}
	if r.Namespace != namespace {
		return fmt.Errorf("record belongs to another namespace")
	}
	if math.IsNaN(r.Confidence) || math.IsInf(r.Confidence, 0) || r.Confidence < 0 || r.Confidence > 1 {
		return fmt.Errorf("invalid confidence")
	}
	if r.Lifecycle == "" {
		return fmt.Errorf("explicit lifecycle required")
	}
	switch kind {
	case "general":
		if r.Scope != (Scope{"global", "_global"}) {
			return fmt.Errorf("general image only accepts global records")
		}
	case "kb":
		if r.Scope.Type != "global" && r.Scope.Type != "workspace" && r.Scope.Type != "project" {
			return fmt.Errorf("KB image cannot contain user records")
		}
		if r.Scope.Value == "" || (r.Scope.Type == "global" && r.Scope.Value != "_global") {
			return fmt.Errorf("invalid KB scope")
		}
	case "server":
		if r.Scope != (Scope{"user", "_user"}) {
			return fmt.Errorf("server image only accepts instance-local user records")
		}
	default:
		return fmt.Errorf("invalid layer kind")
	}
	for _, ts := range []string{r.ValidFrom, r.ValidUntil} {
		if ts != "" {
			if _, err := time.Parse(time.RFC3339Nano, ts); err != nil {
				return fmt.Errorf("timestamps must be RFC3339: %w", err)
			}
		}
	}
	if r.ValidFrom != "" && r.ValidUntil != "" {
		a, _ := time.Parse(time.RFC3339Nano, r.ValidFrom)
		b, _ := time.Parse(time.RFC3339Nano, r.ValidUntil)
		if !a.Before(b) {
			return fmt.Errorf("invalid temporal interval")
		}
	}
	if r.Redirect != nil {
		if err := validateRef(*r.Redirect); err != nil {
			return err
		}
	}
	for _, e := range r.Edges {
		if e.Relation == "" {
			return fmt.Errorf("edge relation required")
		}
		if err := validateRef(e.Target); err != nil {
			return err
		}
	}
	return nil
}

// Terms is the version-1 lexical index codec, not Aimee's semantic ranker.
// Identifiers retain internal dots/hyphens/underscores.
func Terms(text string) []string {
	parts := strings.FieldsFunc(strings.ToLower(text), func(r rune) bool {
		return !unicode.IsLetter(r) && !unicode.IsDigit(r) && r != '-' && r != '_' && r != '.'
	})
	seen := map[string]bool{}
	out := []string{}
	for _, p := range parts {
		p = strings.Trim(p, "-_.")
		if p != "" && !seen[p] {
			seen[p] = true
			out = append(out, p)
		}
	}
	return out
}
