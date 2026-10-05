package sparse

import (
	"encoding/json"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func routedFixture(t *testing.T, routes func([]Record) []CandidateRoute) (*PublishedReader, []Record) {
	t.Helper()
	src, _, records, a, pub, key := authorizationFixture(t)
	a.CandidateRoutes = routes(records)
	dst := Store{filepath.Join(t.TempDir(), "published")}
	id, err := src.CompileAuthorized(dst, signedGrant(t, a, key), pub, a.Subject, a.PolicyEpoch, testNow)
	if err != nil {
		t.Fatal(err)
	}
	reader, err := dst.OpenPublished(id)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(reader.Close)
	return reader, records
}
func bundle(records []Record) []CandidateRoute {
	return []CandidateRoute{{Partition: "alpha", Authority: "test", Cues: []string{"neris", "relay alias"}, Records: []Ref{records[1].Ref, records[0].Ref}}}
}
func TestNativeRouteCompleteBundleAndAddressBinding(t *testing.T) {
	p, records := routedFixture(t, bundle)
	address := NativeAddress{Schema: 1, View: p.View.ID, Representation: "attention-token-spans-v1", Step: 9}
	r, e := p.RouteNative(address, "Which code is downstream of NERIS?", 2, "test", testNow)
	if e != nil || r.Outcome != "hit" || r.CandidateRecords != 2 || r.CandidatePartitions != 1 || r.Fallback {
		t.Fatalf("%+v %v", r, e)
	}
	refs, e := p.ResolveLocal(r.Response, testNow)
	if e != nil || len(refs) != 2 || refs[0] != records[1].Ref || refs[1] != records[0].Ref {
		t.Fatalf("%v %v", refs, e)
	}
	for _, representation := range []string{"text-query-v1", "attention-token-spans-v1"} {
		address.Representation = representation
		for _, query := range []string{"Please inspect Neris now.", "RELAY alias?"} {
			if r, e := p.RouteNative(address, query, 2, "test", testNow); e != nil || r.Outcome != "hit" {
				t.Fatalf("%+v %v", r, e)
			}
		}
	}
	for _, mutate := range []func(*NativeAddress){func(a *NativeAddress) { a.Schema = 2 }, func(a *NativeAddress) { a.View = "other" }, func(a *NativeAddress) { a.Representation = "unknown" }, func(a *NativeAddress) { a.Partitions = []string{"alpha", "alpha"} }} {
		invalid := address
		mutate(&invalid)
		if _, e := p.RouteNative(invalid, "neris", 2, "test", testNow); e == nil {
			t.Fatal("invalid address accepted")
		}
	}
	if r, e := p.RouteNative(address, "neris", 1, "test", testNow); e != nil || r.Outcome != "over_budget" || len(r.Response) != 0 {
		t.Fatalf("partial bundle leaked: %+v %v", r, e)
	}
	address.Partitions = []string{"wrong"}
	if r, e := p.RouteNative(address, "neris", 2, "test", testNow); e != nil || !r.Fallback || r.Outcome == "hit" {
		t.Fatalf("hint expanded routing: %+v %v", r, e)
	}
	address.Partitions = nil
	if r, e := p.RouteNative(address, "neris", 2, "other", testNow); e != nil || r.Outcome == "hit" {
		t.Fatalf("authority crossed: %+v %v", r, e)
	}
	legacy, e := p.Recall("neris", 2, "test", testNow)
	if e != nil || legacy.Outcome != "hit" {
		t.Fatalf("standard preparation path did not route: %+v %v", legacy, e)
	}
	var body map[string]any
	json.Unmarshal(legacy.Response, &body)
	body["facts"].([]any)[0].(map[string]any)["content"] = "poison"
	raw, _ := json.Marshal(body)
	if _, e := p.ResolveLocal(raw, testNow); e == nil {
		t.Fatal("poisoned local receipt accepted")
	}
}
func TestNativeRoutePublisherRejectsUnapprovedAndDuplicateRevisions(t *testing.T) {
	for _, which := range []string{"unapproved", "duplicate", "stale", "duplicate cue", "duplicate partition"} {
		t.Run(which, func(t *testing.T) {
			src, _, records, a, pub, key := authorizationFixture(t)
			a.CandidateRoutes = bundle(records)
			switch which {
			case "unapproved":
				a.CandidateRoutes[0].Records = append(a.CandidateRoutes[0].Records, records[2].Ref)
			case "duplicate":
				a.CandidateRoutes[0].Records = append(a.CandidateRoutes[0].Records, records[0].Ref)
			case "stale":
				a.CandidateRoutes[0].Records[0].Revision = "old"
			case "duplicate cue":
				a.CandidateRoutes[0].Cues = append(a.CandidateRoutes[0].Cues, "NERIS")
			case "duplicate partition":
				a.CandidateRoutes = append(a.CandidateRoutes, a.CandidateRoutes[0])
			}
			if _, e := src.CompileAuthorized(Store{filepath.Join(t.TempDir(), "out")}, signedGrant(t, a, key), pub, a.Subject, a.PolicyEpoch, testNow); e == nil {
				t.Fatal("invalid owner route compiled")
			}
		})
	}
}
func TestNativeRouteCollisionFailsClosed(t *testing.T) {
	p, _ := routedFixture(t, func(rs []Record) []CandidateRoute {
		return []CandidateRoute{{Partition: "one", Authority: "test", Cues: []string{"same"}, Records: []Ref{rs[0].Ref}}, {Partition: "two", Authority: "test", Cues: []string{"same"}, Records: []Ref{rs[1].Ref}}}
	})
	r, e := p.RouteNative(NativeAddress{Schema: 1, View: p.View.ID, Representation: "text-query-v1"}, "same", 2, "test", testNow)
	if e != nil || r.Outcome != "ambiguous" || len(r.Response) != 0 {
		t.Fatalf("%+v %v", r, e)
	}
}

func TestReleasedBundleRevisionDeletionTemporalAndNoInheritance(t *testing.T) {
	base, baseID, dst, row, cues := overlayFixture(t)
	row.ValidUntil = testNow.Add(time.Hour).Format(time.RFC3339)
	routes := []CandidateRoute{{Partition: "drink", Authority: "test", Cues: []string{"drink", "user/drink"}, Records: []Ref{row.Ref}}}
	first, e := dst.CompileReleasedRoutes(base, baseID, "first", "personal", "test", []Record{row}, cues, routes, testNow)
	if e != nil {
		t.Fatal(e)
	}
	p, e := dst.OpenPublished(first)
	if e != nil {
		t.Fatal(e)
	}
	defer p.Close()
	address := NativeAddress{Schema: 1, View: first, Representation: "text-query-v1"}
	if r, e := p.RouteNative(address, "user/drink", 2, "test", testNow); e != nil || r.Outcome != "hit" {
		t.Fatalf("%+v %v", r, e)
	}
	if r, e := p.RouteNative(address, "drink", 2, "test", testNow.Add(time.Hour)); e != nil || r.Outcome != "source_unavailable" || len(r.Response) > 0 {
		t.Fatalf("expired record returned: %+v %v", r, e)
	}
	row.Revision = "2"
	row.Content = "mint"
	row.ValidUntil = ""
	cues[0].Ref = row.Ref
	routes[0].Records = []Ref{row.Ref}
	second, e := dst.CompileReleasedRoutes(base, baseID, "second", "personal", "test", []Record{row}, cues, routes, testNow)
	if e != nil {
		t.Fatal(e)
	}
	q, e := dst.OpenPublished(second)
	if e != nil {
		t.Fatal(e)
	}
	defer q.Close()
	if _, e = q.RouteNative(address, "drink", 2, "test", testNow); e == nil {
		t.Fatal("old address binding crossed publication")
	}
	address.View = second
	r, e := q.RouteNative(address, "drink", 2, "test", testNow)
	if e != nil || r.Outcome != "hit" || !strings.Contains(string(r.Response), "mint") || strings.Contains(string(r.Response), "oolong") {
		t.Fatalf("%+v %v", r, e)
	}
	// Retiring a route is explicit even if its records remain published.
	third, e := dst.CompileReleased(base, baseID, "third", "personal", "test", []Record{row}, cues, testNow)
	if e != nil {
		t.Fatal(e)
	}
	gone, e := dst.OpenPublished(third)
	if e != nil {
		t.Fatal(e)
	}
	defer gone.Close()
	address.View = third
	if r, e := gone.RouteNative(address, "user/drink", 2, "test", testNow); e != nil || r.Outcome == "hit" {
		t.Fatalf("route resurrected: %+v %v", r, e)
	}
	// Deleted rows cannot be named by newly supplied routing metadata.
	if _, e := dst.CompileReleasedRoutes(base, baseID, "deleted", "personal", "test", nil, nil, routes, testNow); e == nil {
		t.Fatal("deleted target compiled")
	}
	delta, e := DiffPublished(p, q)
	if e != nil {
		t.Fatal(e)
	}
	replica := Store{filepath.Join(t.TempDir(), "replica")}
	if e = MaterializeDelta(dst, replica, delta); e != nil {
		t.Fatal(e)
	}
	restored, e := replica.OpenPublished(second)
	if e != nil {
		t.Fatal(e)
	}
	defer restored.Close()
	address.View = second
	if r, e := restored.RouteNative(address, "drink", 2, "test", testNow); e != nil || r.Outcome != "hit" {
		t.Fatalf("route lost in delta: %+v %v", r, e)
	}
}
