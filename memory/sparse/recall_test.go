package sparse

import (
	"encoding/json"
	"testing"
	"time"
)

func TestPublishedRecallFallsBackOutsideAuthorityContract(t *testing.T) {
	s := Store{t.TempDir()}
	r := record("general", "1", "drink oolong")
	c := changes("general", "general", "", r)
	response := json.RawMessage(`{"status":"ok","facts":[{"id":1,"content":"drink oolong","confidence":1}],"windows":[],"evidence":{"source":"s1"}}`)
	c.ReadContracts = []ReadContract{{Query: "What drink?", Limit: 2, Authority: "aimee-test", ValidUntil: testNow.Add(time.Minute).Format(time.RFC3339), Dependencies: []Ref{r.Ref}, Response: response}}
	first := build(t, s, c)
	v := open(t, s, first)
	result := v.Recall("What drink?", 2, "aimee-test", nil, testNow)
	if result.Outcome != "hit" || string(result.Response) != string(response) {
		t.Fatalf("changed authority response: %+v", result)
	}
	for _, tc := range []struct {
		query, authority string
		limit            int
		grants           map[string]bool
		now              time.Time
	}{
		{"What beverage?", "aimee-test", 2, nil, testNow},
		{"What drink?", "another-authority", 2, nil, testNow},
		{"What drink?", "aimee-test", 1, nil, testNow},
		{"What drink?", "aimee-test", 2, userGrant, testNow},
		{"What drink?", "aimee-test", 2, nil, testNow.Add(time.Minute)},
	} {
		if v.Recall(tc.query, tc.limit, tc.authority, tc.grants, tc.now).Outcome == "hit" {
			t.Fatalf("unauthorized reuse: %+v", tc)
		}
	}
	// New knowledge may contradict old results without editing returned records.
	// Publishing any generation withdraws previous contracts unless reissued.
	c.Previous = first
	c.Generation = 2
	c.Records = []Record{record("general", "2", "drink coffee")}
	c.ReadContracts = nil
	second := build(t, s, c)
	if open(t, s, second).Recall("What drink?", 2, "aimee-test", nil, testNow).Outcome != "uncovered" {
		t.Fatal("old decision survived new generation")
	}
	if v.Recall("What drink?", 2, "aimee-test", nil, testNow).Outcome != "hit" {
		t.Fatal("pinned generation changed")
	}
}
func TestPublishedRecallCannotInventContentOrResurrectRetiredSource(t *testing.T) {
	s := Store{t.TempDir()}
	r := record("general", "1", "drink oolong")
	r.Lifecycle = "retired"
	c := changes("general", "general", "", r)
	c.ReadContracts = []ReadContract{{Query: "drink", Limit: 1, Authority: "a", ValidUntil: testNow.Add(time.Hour).Format(time.RFC3339), Dependencies: []Ref{r.Ref}, Response: json.RawMessage(`{"facts":[{"id":"1","content":"drink oolong"}],"windows":[]}`)}}
	v := open(t, s, build(t, s, c))
	if v.Recall("drink", 1, "a", nil, testNow).Outcome != "source_unavailable" {
		t.Fatal("retired source leaked")
	}
	c.ReadContracts[0].Response = json.RawMessage(`{"facts":[{"id":"1","content":"drink coffee"}],"windows":[]}`)
	if _, err := s.Build(c); err == nil {
		t.Fatal("forged response accepted")
	}
}
