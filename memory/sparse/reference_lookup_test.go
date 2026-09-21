package sparse

import (
	"encoding/json"
	"testing"
	"time"
)

func TestPublicReferenceLookup(t *testing.T) {
	s := Store{t.TempDir()}
	a := record("general", "a", "IANA service alpha")
	a.Content = "TCP port 12345"
	a.ValidUntil = testNow.Add(time.Hour).Format(time.RFC3339)
	b := record("general", "b", "planet beta")
	b.Content = "orbital period 9.1 days"
	hidden := record("general", "c", "planet hidden")
	hidden.Content = "excluded canary"
	head := build(t, s, changes("general", "general", "", a, b, hidden))
	v := open(t, s, head)
	grant := Authorization{Grants: []string{}, Records: []AuthorizedRecord{AuthorizeRecord(a), AuthorizeRecord(b)}, ReferenceLookups: []ReferenceLookupPolicy{{"general", "test", "exact-key-v1"}}}
	l, err := NewReferenceLookup(v, grant)
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct {
		q               string
		limit           int
		authority, want string
		count           int
	}{
		{"What is the TCP port for IANA service alpha?", 2, "test", "hit", 1},
		{"For IANA SERVICE alpha, give the assigned port.", 2, "test", "hit", 1},
		{"IANA service alphabet", 2, "test", "uncovered", 0},
		{"planet hidden", 2, "test", "uncovered", 0},
		{"IANA service alpha and planet beta", 2, "test", "hit", 2},
		{"IANA service alpha and planet beta", 1, "test", "over_budget", 0},
		{"IANA service alpha", 2, "wrong", "uncovered", 0},
	} {
		t.Run(tc.q+tc.authority+string(rune(tc.limit)), func(t *testing.T) {
			got := l.Recall(tc.q, tc.limit, tc.authority, testNow)
			if got.Outcome != tc.want {
				t.Fatalf("%+v", got)
			}
			if tc.count > 0 {
				var body struct{ Facts []any }
				if json.Unmarshal(got.Response, &body) != nil || len(body.Facts) != tc.count {
					t.Fatal(string(got.Response))
				}
			}
		})
	}
	if got := l.Recall("IANA service alpha", 2, "test", testNow.Add(2*time.Hour)); got.Outcome != "source_unavailable" {
		t.Fatal(got)
	}
	grant.ReferenceLookups = nil
	l, err = NewReferenceLookup(v, grant)
	if err != nil {
		t.Fatal(err)
	}
	if l.Recall("planet beta", 2, "test", testNow).Outcome != "uncovered" {
		t.Fatal("global scope inferred permission")
	}
}
func TestReferenceLookupRejectsAmbiguityAndPrivateLayer(t *testing.T) {
	s := Store{t.TempDir()}
	a := record("general", "a", "planet duplicate")
	b := record("general", "b", "planet duplicate")
	b.Content = "different answer"
	head := build(t, s, changes("general", "general", "", a, b))
	v := open(t, s, head)
	grant := Authorization{Records: []AuthorizedRecord{AuthorizeRecord(a), AuthorizeRecord(b)}, ReferenceLookups: []ReferenceLookupPolicy{{"general", "test", "exact-key-v1"}}}
	l, err := NewReferenceLookup(v, grant)
	if err != nil {
		t.Fatal(err)
	}
	if l.Recall("planet duplicate", 2, "test", testNow).Outcome != "ambiguous" {
		t.Fatal("ambiguous key selected")
	}
	private := record("user", "a", "private object")
	tip := build(t, s, changes("user", "server", head, private))
	pv := open(t, s, tip)
	grant.Records = append(grant.Records, AuthorizeRecord(private))
	grant.ReferenceLookups = []ReferenceLookupPolicy{{"user", "test", "exact-key-v1"}}
	if _, err = NewReferenceLookup(pv, grant); err == nil {
		t.Fatal("private facts became public lookup")
	}
	grant.ReferenceLookups = []ReferenceLookupPolicy{{"general", "test", "semantic-v999"}}
	if _, err = NewReferenceLookup(v, grant); err == nil {
		t.Fatal("unsupported policy accepted")
	}
}

func TestReferenceIdentifierPunctuationIsSignificant(t *testing.T) {
	s := Store{t.TempDir()}
	records := []Record{}
	for _, name := range []string{"pxc", "pxc-spvr-ft", "foo-bar", "foo_bar", "cl/1", "cl-1"} {
		records = append(records, record("general", name, "IANA service "+name))
	}
	head := build(t, s, changes("general", "general", "", records...))
	v := open(t, s, head)
	grant := Authorization{ReferenceLookups: []ReferenceLookupPolicy{{"general", "test", "exact-key-v1"}}}
	for _, r := range records {
		grant.Records = append(grant.Records, AuthorizeRecord(r))
	}
	l, err := NewReferenceLookup(v, grant)
	if err != nil {
		t.Fatal(err)
	}
	for _, r := range records {
		result := l.Recall("What port is used by "+r.Key+"?", 4, "test", testNow)
		var body struct{ Facts []struct{ ID string } }
		if result.Outcome != "hit" || json.Unmarshal(result.Response, &body) != nil || len(body.Facts) != 1 || body.Facts[0].ID != r.ID {
			t.Fatalf("wrong entity for %s: %s", r.Key, result.Response)
		}
	}
}

func TestReferenceLongestNameAndTwoExplicitNames(t *testing.T) {
	s := Store{t.TempDir()}
	a := record("general", "mass", "constant electron mass")
	b := record("general", "energy", "constant electron mass energy equivalent")
	head := build(t, s, changes("general", "general", "", a, b))
	v := open(t, s, head)
	grant := Authorization{Records: []AuthorizedRecord{AuthorizeRecord(a), AuthorizeRecord(b)}, ReferenceLookups: []ReferenceLookupPolicy{{"general", "test", "exact-key-v1"}}}
	l, err := NewReferenceLookup(v, grant)
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct {
		q     string
		count int
	}{
		{"Give constant electron mass energy equivalent.", 1},
		{"Give constant electron mass and constant electron mass energy equivalent.", 2},
	} {
		r := l.Recall(tc.q, 4, "test", testNow)
		var body struct{ Facts []struct{ ID string } }
		if r.Outcome != "hit" || json.Unmarshal(r.Response, &body) != nil || len(body.Facts) != tc.count {
			t.Fatalf("bad name resolution: %s", r.Response)
		}
		if tc.count == 1 && body.Facts[0].ID != "energy" {
			t.Fatal("shorter name activated")
		}
	}
}
