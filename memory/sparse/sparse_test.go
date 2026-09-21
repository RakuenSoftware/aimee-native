package sparse

import (
	"archive/tar"
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"reflect"
	"strings"
	"sync"
	"testing"
	"time"
)

var testNow = time.Date(2026, 9, 20, 12, 0, 0, 0, time.UTC)
var userGrant = map[string]bool{"user:_user": true}

func record(ns, id, text string) Record {
	scope := Scope{"global", "_global"}
	if ns == "user" {
		scope = Scope{"user", "_user"}
	}
	return Record{Ref: Ref{ns, id, "v1"}, Scope: scope, Key: text, Content: text, Kind: "fact", Tier: "L3", Confidence: 1, Lifecycle: "active"}
}
func changes(ns, kind, up string, records ...Record) ChangeSet {
	return ChangeSet{Namespace: ns, Kind: kind, Generation: 1, Upstream: up, Records: records, Source: "test-authority", Coverage: []string{"test-memory-records"}}
}
func build(t testing.TB, s Store, c ChangeSet) string {
	t.Helper()
	id, err := s.Build(c)
	if err != nil {
		t.Fatal(err)
	}
	return id
}
func open(t testing.TB, s Store, id string) *View {
	t.Helper()
	v, err := s.Open(id)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(v.Close)
	return v
}
func search(t testing.TB, v *View, q string, g map[string]bool) SearchResult {
	t.Helper()
	r, err := v.Search(q, 16, 8192, g, testNow)
	if err != nil {
		t.Fatal(err)
	}
	return r
}

func TestDirectAndKBEnrichedPathsPreserveIdentitiesAndGraph(t *testing.T) {
	s := Store{t.TempDir()}
	general := record("general", "1", "workstation general specification")
	g := build(t, s, changes("general", "general", "", general))
	kb := record("kb", "1", "workstation project constraint")
	kb.Scope = Scope{"project", "aimee"}
	k := build(t, s, changes("kb", "kb", g, kb))
	local := record("user", "1", "workstation local configuration")
	local.Edges = []Edge{{"device", general.Ref}, {"requirement", kb.Ref}}
	u := build(t, s, changes("user", "server", k, local))
	v := open(t, s, u)
	grants := map[string]bool{"user:_user": true, "project:aimee": true}
	r := search(t, v, "workstation", grants)
	if len(r.Records) != 3 || r.Candidates != 3 {
		t.Fatalf("combined: %+v", r)
	}
	seen := map[string]bool{}
	for _, x := range r.Records {
		seen[x.Ref.Key()] = true
	}
	if len(seen) != 3 {
		t.Fatal("colliding numeric IDs merged")
	}
	if n, err := v.Neighbors(local.Ref, grants, testNow); err != nil || len(n) != 2 {
		t.Fatalf("graph: %v %v", n, err)
	}
	if _, err := v.Neighbors(local.Ref, userGrant, testNow); err == nil {
		t.Fatal("graph crossed project scope")
	}
	if len(search(t, v, "workstation", nil).Records) != 1 {
		t.Fatal("private or project data leaked")
	}
	local.Edges = []Edge{{"device", general.Ref}}
	direct := build(t, s, changes("user", "server", g, local))
	if len(search(t, open(t, s, direct), "workstation", userGrant).Records) != 2 {
		t.Fatal("standalone path failed")
	}
}

func TestDeltaPublicationKeepsPinnedReadersAndRejectsLostUpdates(t *testing.T) {
	s := Store{t.TempDir()}
	g := build(t, s, changes("general", "general", "", record("general", "1", "device base")))
	a := record("user", "1", "drink oolong")
	u := build(t, s, changes("user", "server", g, a))
	if err := s.Publish(u, ""); err != nil {
		t.Fatal(err)
	}
	old := open(t, s, u)
	a.Content = "drink coffee"
	a.Key = a.Content
	a.Revision = "v2"
	c := changes("user", "server", g, a)
	c.Generation = 2
	c.Previous = u
	next := build(t, s, c)
	if err := s.Publish(next, ""); err == nil {
		t.Fatal("lost update accepted")
	}
	if err := s.Publish(next, u); err != nil {
		t.Fatal(err)
	}
	if search(t, old, "drink", userGrant).Records[0].Content != "drink oolong" {
		t.Fatal("pinned view changed")
	}
	if search(t, open(t, s, next), "drink", userGrant).Records[0].Content != "drink coffee" {
		t.Fatal("delta not applied")
	}
	c.Previous = next
	c.Generation = 3
	c.Records = nil
	c.Delete = []Ref{a.Ref}
	deleted := build(t, s, c)
	if len(search(t, open(t, s, deleted), "drink", userGrant).Records) != 0 {
		t.Fatal("tombstone not applied")
	}
	if search(t, old, "drink", userGrant).Records[0].Revision != "v1" {
		t.Fatal("old snapshot not retained")
	}
	c.Delete = []Ref{{"general", "1", "v1"}}
	if _, err := s.Build(c); err == nil {
		t.Fatal("foreign deletion accepted")
	}
}

func TestNoImplicitOverrideAndScopedAuthoritativeResolution(t *testing.T) {
	s := Store{t.TempDir()}
	a := record("general", "1", "release old")
	g := build(t, s, changes("general", "general", "", a))
	b := record("user", "1", "release new")
	u := build(t, s, changes("user", "server", g, b))
	if len(search(t, open(t, s, u), "release", userGrant).Records) != 2 {
		t.Fatal("implicit last-layer-wins")
	}
	c := changes("user", "server", g)
	c.Previous = u
	c.Generation = 2
	c.Suppressions = []Suppression{{Target: a.Ref, Reason: "Aimee resolved this local correction", Scope: Scope{"user", "_user"}}}
	next := build(t, s, c)
	v := open(t, s, next)
	if r := search(t, v, "release", userGrant); len(r.Records) != 1 || r.Records[0].Namespace != "user" {
		t.Fatalf("resolution failed: %+v", r)
	}
	if r := search(t, v, "release", nil); len(r.Records) != 1 || r.Records[0].Namespace != "general" {
		t.Fatal("private resolution affected unauthorized view")
	}
	c.Previous = next
	c.Generation = 3
	c.Suppressions[0].Release = true
	released := build(t, s, c)
	if len(search(t, open(t, s, released), "release", userGrant).Records) != 2 {
		t.Fatal("resolution release failed")
	}
	a.Revision = "v2"
	a.Content = "release corrected upstream"
	a.Key = a.Content
	gc := changes("general", "general", "", a)
	gc.Previous = g
	gc.Generation = 2
	g2 := build(t, s, gc)
	c.Previous = next
	c.Upstream = g2
	c.Generation = 4
	c.Suppressions = nil
	if _, err := s.Build(c); err == nil || !strings.Contains(err.Error(), "reconciliation") {
		t.Fatalf("stale resolution accepted: %v", err)
	}
}

func TestAliasesDedupAndTemporalLifecycle(t *testing.T) {
	s := Store{t.TempDir()}
	a := record("general", "1", "device teal")
	a.Aliases = []string{"beacon"}
	alias := record("general", "2", "beacon")
	alias.Redirect = &a.Ref
	retired := record("general", "3", "beacon retired")
	retired.Lifecycle = "retired"
	expired := record("general", "4", "beacon expired")
	expired.ValidUntil = testNow.Format(time.RFC3339)
	future := record("general", "5", "beacon future")
	future.ValidFrom = testNow.Add(time.Second).Format(time.RFC3339)
	suppressed := record("general", "6", "beacon suppressed")
	suppressed.Suppressed = true
	g := build(t, s, changes("general", "general", "", a, alias, retired, expired, future, suppressed))
	r := search(t, open(t, s, g), "beacon", nil)
	if len(r.Records) != 1 || r.Records[0].ID != "1" {
		t.Fatalf("dedup/validity failed: %+v", r)
	}
	a.Redirect = &alias.Ref
	if _, err := s.Build(changes("general", "general", "", a, alias)); err == nil {
		t.Fatal("redirect cycle accepted")
	}
}

func TestCorruptionAndIncompletePublishLeaveCurrentUntouched(t *testing.T) {
	s := Store{t.TempDir()}
	g := build(t, s, changes("general", "general", "", record("general", "1", "needle")))
	if err := s.Publish(g, ""); err != nil {
		t.Fatal(err)
	}
	if err := s.Publish(strings.Repeat("a", 64), g); err == nil {
		t.Fatal("missing generation published")
	}
	if cur, _ := s.Current(); cur != g {
		t.Fatal("CURRENT changed after failed publish")
	}
	m, _ := s.manifest(g)
	path, _ := s.object(m.Data)
	f, err := os.OpenFile(path, os.O_WRONLY, 0600)
	if err != nil {
		t.Fatal(err)
	}
	_, err = f.WriteAt([]byte("!"), 0)
	f.Close()
	if err != nil {
		t.Fatal(err)
	}
	v := open(t, s, g)
	if _, err := v.Search("needle", 4, 100, nil, testNow); err == nil {
		t.Fatal("corrupt payload delivered")
	}
	if err := v.Verify(); err == nil {
		t.Fatal("verify ignored corruption")
	}
}

func TestRejectsWrongLayerScopeAndRevisionReuse(t *testing.T) {
	s := Store{t.TempDir()}
	a := record("general", "1", "old")
	g := build(t, s, changes("general", "general", "", a))
	a.Content = "new"
	c := changes("general", "general", "", a)
	c.Previous = g
	c.Generation = 2
	if _, err := s.Build(c); err == nil {
		t.Fatal("revision reuse accepted")
	}
	if _, err := s.Build(changes("user", "general", "", record("user", "1", "private"))); err == nil {
		t.Fatal("private general publication accepted")
	}
	k := build(t, s, changes("kb", "kb", g, record("kb", "1", "kb")))
	if _, err := s.Build(changes("other", "kb", k)); err == nil {
		t.Fatal("KB-on-KB accepted")
	}
	u := build(t, s, changes("user", "server", k, record("user", "1", "local")))
	if _, err := s.Build(changes("other", "server", u)); err == nil {
		t.Fatal("server-on-server accepted")
	}
}

func TestCandidateOverflowIsVisibleAndPayloadReadsAreSparse(t *testing.T) {
	s := Store{t.TempDir()}
	records := []Record{}
	for i := 0; i < 200; i++ {
		records = append(records, record("general", fmt.Sprint(i), fmt.Sprintf("common unique-%d payload", i)))
	}
	g := build(t, s, changes("general", "general", "", records...))
	v := open(t, s, g)
	if _, err := v.Search("common", 1, 10, nil, testNow); err == nil {
		t.Fatal("broad query silently truncated")
	}
	r := search(t, v, "unique-132", nil)
	if len(r.Records) != 1 || r.Candidates != 1 || r.BytesRead > 1024 {
		t.Fatalf("not sparse: %+v", r)
	}
}

func TestConcurrentPinnedReadsDuringPublication(t *testing.T) {
	s := Store{t.TempDir()}
	a := record("general", "1", "needle old")
	g := build(t, s, changes("general", "general", "", a))
	if err := s.Publish(g, ""); err != nil {
		t.Fatal(err)
	}
	v := open(t, s, g)
	a.Revision = "v2"
	a.Content = "needle new"
	c := changes("general", "general", "", a)
	c.Previous = g
	c.Generation = 2
	g2 := build(t, s, c)
	var wg sync.WaitGroup
	for range 8 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for range 30 {
				r, err := v.Search("needle", 4, 100, nil, testNow)
				if err != nil || len(r.Records) != 1 || r.Records[0].Revision != "v1" {
					t.Errorf("pinned read: %v %v", r, err)
				}
			}
		}()
	}
	if err := s.Publish(g2, g); err != nil {
		t.Fatal(err)
	}
	wg.Wait()
}

func TestSourceMetadataAndReferencesRoundTrip(t *testing.T) {
	s := Store{t.TempDir()}
	a := record("general", "1", "fact")
	a.Metadata = json.RawMessage(`{"provenance":["source-a"],"confidence_evidence":{"positive":3,"negative":1}}`)
	g := build(t, s, changes("general", "general", "", a))
	got, err := open(t, s, g).Get(a.Ref, nil, testNow)
	if err != nil || !reflect.DeepEqual(got, a) {
		t.Fatalf("roundtrip: %+v %v", got, err)
	}
}

func TestBundleCopiesOnlySelectedLineageAndDoesNotPublish(t *testing.T) {
	s := Store{t.TempDir()}
	g := build(t, s, changes("general", "general", "", record("general", "1", "public beacon")))
	_ = build(t, s, changes("user", "server", g, record("user", "1", "private canary")))
	var archive bytes.Buffer
	if err := s.Export(g, &archive); err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(archive.Bytes(), []byte("private canary")) {
		t.Fatal("unrelated private object exported")
	}
	dst := Store{t.TempDir()}
	id, err := dst.Import(bytes.NewReader(archive.Bytes()))
	if err != nil || id != g {
		t.Fatalf("import: %s %v", id, err)
	}
	if _, err = dst.Current(); !os.IsNotExist(err) {
		t.Fatal("import changed CURRENT")
	}
	if err = open(t, dst, id).Verify(); err != nil {
		t.Fatal(err)
	}
}

func TestBundleRejectsPathTraversalAndBadDigest(t *testing.T) {
	for _, name := range []string{"../outside", "objects/" + strings.Repeat("a", 64)} {
		t.Run(name, func(t *testing.T) {
			var archive bytes.Buffer
			tw := tar.NewWriter(&archive)
			if err := tw.WriteHeader(&tar.Header{Name: name, Typeflag: tar.TypeReg, Mode: 0600, Size: 3}); err != nil {
				t.Fatal(err)
			}
			_, _ = tw.Write([]byte("bad"))
			_ = tw.Close()
			s := Store{t.TempDir()}
			if _, err := s.Import(bytes.NewReader(archive.Bytes())); err == nil {
				t.Fatal("unsafe/corrupt bundle accepted")
			}
			if _, err := s.Current(); !os.IsNotExist(err) {
				t.Fatal("bad bundle published")
			}
		})
	}
}

func BenchmarkSparseLookup(b *testing.B) {
	for _, n := range []int{1000, 10000, 100000} {
		b.Run(fmt.Sprint(n), func(b *testing.B) {
			s := Store{b.TempDir()}
			records := make([]Record, n)
			for i := range records {
				records[i] = record("general", fmt.Sprint(i), fmt.Sprintf("unit-%d configuration", i))
			}
			g := build(b, s, changes("general", "general", "", records...))
			v := open(b, s, g)
			b.ReportAllocs()
			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				r, err := v.Search(fmt.Sprintf("unit-%d", i%n), 4, 8192, nil, testNow)
				if err != nil || len(r.Records) != 1 {
					b.Fatal(err)
				}
			}
		})
	}
}
