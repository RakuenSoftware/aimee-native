package sparse

import (
	"encoding/json"
	"fmt"
	"sort"
	"time"
)

// ReadContract is a publisher-authorized, bounded reuse decision. Only the tip
// manifest's contracts apply: any new publication invalidates old decisions
// unless the authority explicitly republishes them. This is not learned routing.
type ReadContract struct {
	Query        string          `json:"query"`
	Limit        int             `json:"limit"`
	Authority    string          `json:"authority"`
	Grants       []string        `json:"grants"`
	ValidUntil   string          `json:"valid_until"`
	Dependencies []Ref           `json:"dependencies"`
	Response     json.RawMessage `json:"response"`
}
type RecallResult struct {
	View     string          `json:"view"`
	Outcome  string          `json:"outcome"`
	Response json.RawMessage `json:"response,omitempty"`
}

func readKey(query string, limit int, authority string, grants []string) string {
	g := append([]string{}, grants...)
	sort.Strings(g)
	b, _ := json.Marshal([]any{query, limit, authority, g})
	return digest(b)
}
func (v *View) loadContracts(contracts []ReadContract) error {
	v.reads = map[string]ReadContract{}
	for _, c := range contracts {
		if c.Query == "" || c.Authority == "" || c.Limit < 1 || c.Limit > 32 {
			return fmt.Errorf("invalid read contract identity")
		}
		if _, err := time.Parse(time.RFC3339Nano, c.ValidUntil); err != nil {
			return fmt.Errorf("read contract needs expiry")
		}
		grants := map[string]bool{}
		for _, g := range c.Grants {
			if g == "" || grants[g] {
				return fmt.Errorf("invalid read contract grants")
			}
			grants[g] = true
		}
		var response struct {
			Facts []struct {
				ID      json.RawMessage `json:"id"`
				Content string          `json:"content"`
			} `json:"facts"`
			Windows []json.RawMessage `json:"windows"`
			Error   json.RawMessage   `json:"error"`
		}
		if json.Unmarshal(c.Response, &response) != nil || len(response.Facts) == 0 || len(response.Facts) > c.Limit || len(response.Facts) != len(c.Dependencies) || len(response.Windows) > 0 || len(response.Error) > 0 {
			return fmt.Errorf("unsupported read contract response")
		}
		for i, ref := range c.Dependencies {
			loc := v.record(ref.Key())
			if loc == nil || loc.entry.Ref != ref {
				return fmt.Errorf("read contract source revision missing")
			}
			record, err := v.read(loc)
			if err != nil {
				return err
			}
			var id string
			if json.Unmarshal(response.Facts[i].ID, &id) != nil {
				id = string(response.Facts[i].ID)
			}
			if id != ref.ID || response.Facts[i].Content != record.Content {
				return fmt.Errorf("read contract response differs from source")
			}
		}
		key := readKey(c.Query, c.Limit, c.Authority, c.Grants)
		if _, ok := v.reads[key]; ok {
			return fmt.Errorf("duplicate read contract")
		}
		v.reads[key] = c
	}
	return nil
}

// Recall does no lexical guessing. An unapproved request falls back to Aimee.
// A contract's publisher owns freshness within its declared validity interval.
func (v *View) Recall(query string, limit int, authority string, grants map[string]bool, now time.Time) RecallResult {
	result := RecallResult{View: v.ID, Outcome: "uncovered"}
	g := []string{}
	for k, allowed := range grants {
		if allowed {
			g = append(g, k)
		}
	}
	c, ok := v.reads[readKey(query, limit, authority, g)]
	if !ok && v.base != nil {
		c, ok = v.base.reads[readKey(query, limit, authority, g)]
	}
	if !ok {
		return result
	}
	expiry, _ := time.Parse(time.RFC3339Nano, c.ValidUntil)
	if !now.Before(expiry) {
		result.Outcome = "expired"
		return result
	}
	for _, ref := range c.Dependencies {
		record, err := v.Get(ref, grants, now)
		if err != nil || record.Ref != ref {
			result.Outcome = "source_unavailable"
			return result
		}
	}
	result.Outcome = "hit"
	result.Response = c.Response
	return result
}
