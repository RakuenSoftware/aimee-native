package sparse

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
)

func overlayFixture(t *testing.T) (Store, string, Store, Record, []ReferenceCue) {
	t.Helper()
	base := Store{filepath.Join(t.TempDir(), "base")}
	r := Record{Ref: Ref{"general", "planet", "1"}, Scope: Scope{"global", "_global"}, Key: "planet mercury", Content: "Mercury is the nearest planet.", Kind: "fact", Lifecycle: "active", Confidence: 1}
	id, e := base.Build(ChangeSet{Namespace: "general", Kind: "general", Generation: 1, Source: "authorized knowledge snapshot", Coverage: []string{"public"}, Authorization: t.Name(), Records: []Record{r}, Serving: &ServingConfig{Version: 1, ReferenceLookups: []ReferenceLookupPolicy{{"general", "test", "exact-key-v1"}}}})
	if e != nil {
		t.Fatal(e)
	}
	row := Record{Ref: Ref{"personal", "drink", "1"}, Scope: Scope{"user", "_user"}, Key: "preferred drink", Content: "oolong", Kind: "fact", Lifecycle: "active", Confidence: 1}
	return base, id, Store{filepath.Join(t.TempDir(), "publisher")}, row, []ReferenceCue{{row.Ref, "preferred drink", "test"}}
}
func compileOverlay(t *testing.T, base Store, id string, dst Store, rows []Record, cues []ReferenceCue, binding string) string {
	t.Helper()
	h, e := dst.CompileReleased(base, id, binding, "personal", "test", rows, cues, testNow)
	if e != nil {
		t.Fatal(e)
	}
	return h
}
func TestOverlayReuseRetrievalAndDelta(t *testing.T) {
	base, id, out, row, cues := overlayFixture(t)
	one := compileOverlay(t, base, id, out, []Record{row}, cues, "one")
	p, e := out.OpenPublished(one)
	if e != nil {
		t.Fatal(e)
	}
	defer p.Close()
	if p.lookup != nil || p.parent.lookup != nil {
		t.Fatal("publication constructed retrieval indexes")
	}
	if len(p.View.records) != 1 || p.View.base == nil {
		t.Fatal("public rows copied into personal map")
	}
	if p.View.Layers[1].Upstream != id || len(p.View.Layers[1].Serving.ReferenceCues) != 1 {
		t.Fatal("base rewritten or cues duplicated")
	}
	r, e := p.Recall("planet mercury and preferred drink", 4, "test", testNow)
	if e != nil || r.Outcome != "hit" || !strings.Contains(string(r.Response), "oolong") || !strings.Contains(string(r.Response), "Mercury") {
		t.Fatalf("%+v %v", r, e)
	}
	oldLookup := p.parent.lookup
	row.Content = "mint"
	row.Revision = "2"
	cues[0].Ref = row.Ref
	two := compileOverlay(t, base, id, out, []Record{row}, cues, "two")
	q, e := out.OpenPublished(two)
	if e != nil {
		t.Fatal(e)
	}
	defer q.Close()
	if q.parent != p.parent || q.parent.lookup != oldLookup {
		t.Fatal("unchanged base reader/index rebuilt")
	}
	d, e := DiffPublished(p, q)
	if e != nil {
		t.Fatal(e)
	}
	if d.Version != 2 || d.Layers[0].ReuseLayer != id || len(d.Layers[1].Upsert) != 1 {
		t.Fatalf("%+v", d)
	}
	replica := Store{filepath.Join(t.TempDir(), "replica")}
	if e = MaterializeDelta(out, replica, d); e != nil {
		t.Fatal(e)
	}
	check, e := replica.OpenPublished(two)
	if e != nil {
		t.Fatal(e)
	}
	defer check.Close()
	r, e = check.Recall("preferred drink", 4, "test", testNow)
	if e != nil || r.Outcome != "hit" || !strings.Contains(string(r.Response), "mint") || strings.Contains(string(r.Response), "oolong") {
		t.Fatalf("%+v %v", r, e)
	}
	if e = out.Publish(two, ""); e != nil {
		t.Fatal(e)
	}
	// A later removal does not resurrect the cached personal value.
	empty := compileOverlay(t, base, id, out, nil, nil, "empty")
	gone, e := out.OpenPublished(empty)
	if e != nil {
		t.Fatal(e)
	}
	defer gone.Close()
	r, e = gone.Recall("preferred drink", 4, "test", testNow)
	if e != nil || r.Outcome != "uncovered" {
		t.Fatalf("%+v %v", r, e)
	}
	if gone.Retain([]RetentionProof{{row.Ref, AuthorizeRecord(row).SHA256}}, testNow)[0] {
		t.Fatal("removed personal encoding retained")
	}
}
func TestOverlayCollisionAndLongestMatch(t *testing.T) {
	base, id, out, row, cues := overlayFixture(t)
	cues[0].Cue = "planet mercury"
	h := compileOverlay(t, base, id, out, []Record{row}, cues, "collision")
	p, e := out.OpenPublished(h)
	if e != nil {
		t.Fatal(e)
	}
	defer p.Close()
	r, e := p.Recall("planet mercury", 4, "test", testNow)
	if e != nil || r.Outcome != "ambiguous" {
		t.Fatalf("%+v %v", r, e)
	}
	cues[0].Cue = "planet mercury preference"
	h = compileOverlay(t, base, id, out, []Record{row}, cues, "longest")
	q, e := out.OpenPublished(h)
	if e != nil {
		t.Fatal(e)
	}
	defer q.Close()
	r, e = q.Recall("planet mercury preference", 4, "test", testNow)
	if e != nil || r.Outcome != "hit" || strings.Contains(string(r.Response), "nearest") {
		t.Fatalf("%+v %v", r, e)
	}
	var wg sync.WaitGroup
	for range 8 {
		wg.Go(func() {
			if _, e := q.Recall("planet mercury", 4, "test", testNow); e != nil {
				t.Error(e)
			}
		})
	}
	wg.Wait()
}
func TestCachedBaseRejectsTamperAndReplacement(t *testing.T) {
	for _, object := range []string{"data", "index", "manifest"} {
		t.Run(object, func(t *testing.T) {
			base, id, out, row, cues := overlayFixture(t)
			h := compileOverlay(t, base, id, out, []Record{row}, cues, "one")
			p, e := out.OpenPublished(h)
			if e != nil {
				t.Fatal(e)
			}
			p.Close()
			m, e := base.manifest(id)
			if e != nil {
				t.Fatal(e)
			}
			hash := map[string]string{"data": m.Data, "index": m.Index, "manifest": id}[object]
			path, _ := out.object(hash)
			raw, e := os.ReadFile(path)
			if e != nil {
				t.Fatal(e)
			}
			info, _ := os.Stat(path)
			// Same inode, length, and restored mtime must still miss the validation cache.
			raw[len(raw)/2] ^= 1
			if e = os.WriteFile(path, raw, 0600); e != nil {
				t.Fatal(e)
			}
			os.Chtimes(path, info.ModTime(), info.ModTime())
			if q, e := out.OpenPublished(h); e == nil {
				q.Close()
				t.Fatal("cached object hid tampering")
			}
		})
	}
}
func TestOverlayFinalCheckStillPreventsRelease(t *testing.T) {
	base, id, out, row, cues := overlayFixture(t)
	h := compileOverlay(t, base, id, out, []Record{row}, cues, "one")
	if e := out.Publish(h, ""); e != nil {
		t.Fatal(e)
	}
	delivery := Delivery{Root: filepath.Join(t.TempDir(), "delivery")}
	calls := 0
	_, e := delivery.install(out, "", os.Getgid(), func() error { calls++; return os.ErrPermission })
	if e == nil || calls != 1 {
		t.Fatalf("check bypassed %d %v", calls, e)
	}
	if current, _ := delivery.current(); current != "" {
		t.Fatal("denied generation published")
	}
}
func TestPrivateHistoryCompactionAndResume(t *testing.T) {
	base, id, out, row, cues := overlayFixture(t)
	var first string
	last := ""
	os.MkdirAll(out.Root, 0700)
	os.WriteFile(filepath.Join(out.Root, "RECIPIENT"), []byte("test"), 0600)
	for _, value := range []string{"oolong", "mint", "tea", "water"} {
		row.Content = value
		row.Revision = value
		cues[0].Ref = row.Ref
		h := compileOverlay(t, base, id, out, []Record{row}, cues, value)
		if first == "" {
			first = h
		}
		if e := out.Publish(h, last); e != nil {
			t.Fatal(e)
		}
		last = h
		if e := out.RememberPublication(h); e != nil {
			t.Fatal(e)
		}
	}
	n, e := out.CompactPublicationHistory(2)
	if e != nil || n == 0 {
		t.Fatalf("%d %v", n, e)
	}
	if _, e = out.OpenPublished(first); e == nil {
		t.Fatal("old checkpoint not pruned")
	}
	p, e := out.OpenPublished(last)
	if e != nil {
		t.Fatal(e)
	}
	defer p.Close()
	d, e := DiffPublished(nil, p)
	if e != nil {
		t.Fatal(e)
	}
	dst := Store{filepath.Join(t.TempDir(), "reset")}
	if e = MaterializeDelta(Store{}, dst, d); e != nil {
		t.Fatal(e)
	}
	raw, _ := json.Marshal(d)
	if strings.Contains(string(raw), "oolong") {
		t.Fatal("compaction/full reset leaked obsolete row")
	}
}

func TestBaseCacheChecksPinnedInodeAfterReplacement(t *testing.T) {
	base, id, out, row, cues := overlayFixture(t)
	h := compileOverlay(t, base, id, out, []Record{row}, cues, "one")
	p, e := out.OpenPublished(h)
	if e != nil {
		t.Fatal(e)
	}
	defer p.Close()
	m, _ := base.manifest(id)
	path, _ := out.object(m.Data)
	original, e := os.ReadFile(path)
	if e != nil {
		t.Fatal(e)
	}
	// Replace the recipient path with correct bytes, then corrupt the original
	// pinned inode via its other hard link. Both paths must be checked on reuse.
	if e = os.Remove(path); e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(path, original, 0600); e != nil {
		t.Fatal(e)
	}
	old, _ := base.object(m.Data)
	original[len(original)/2] ^= 1
	if e = os.WriteFile(old, original, 0600); e != nil {
		t.Fatal(e)
	}
	if q, e := out.OpenPublished(h); e == nil {
		q.Close()
		t.Fatal("replacement hid corrupted pinned inode")
	}
}

func TestOverlayIsolationAndMalformedBaseReuse(t *testing.T) {
	base, id, out, row, cues := overlayFixture(t)
	one := compileOverlay(t, base, id, out, []Record{row}, cues, "recipient-one")
	p, e := out.OpenPublished(one)
	if e != nil {
		t.Fatal(e)
	}
	defer p.Close()
	row.Content = "recipient two secret"
	row.Revision = "2"
	cues[0].Ref = row.Ref
	two := compileOverlay(t, base, id, out, []Record{row}, cues, "recipient-two")
	q, e := out.OpenPublished(two)
	if e != nil {
		t.Fatal(e)
	}
	defer q.Close()
	for _, test := range []struct {
		reader         *PublishedReader
		want, unwanted string
	}{{p, "oolong", "recipient two secret"}, {q, "recipient two secret", "oolong"}} {
		got, e := test.reader.Recall("preferred drink", 4, "test", testNow)
		if e != nil || !strings.Contains(string(got.Response), test.want) || strings.Contains(string(got.Response), test.unwanted) {
			t.Fatalf("%+v %v", got, e)
		}
	}
	d, e := DiffPublished(p, q)
	if e != nil {
		t.Fatal(e)
	}
	d.Layers[0].Upsert = []Record{row}
	if e = MaterializeDelta(out, Store{filepath.Join(t.TempDir(), "invalid")}, d); e == nil {
		t.Fatal("accepted mutation of reused immutable base")
	}
}

func TestExplicitOverlayVerifyIncludesBase(t *testing.T) {
	base, id, out, row, cues := overlayFixture(t)
	h := compileOverlay(t, base, id, out, []Record{row}, cues, "one")
	p, e := out.OpenPublished(h)
	if e != nil {
		t.Fatal(e)
	}
	defer p.Close()
	m, _ := base.manifest(id)
	file, _ := base.object(m.Data)
	raw, e := os.ReadFile(file)
	if e != nil {
		t.Fatal(e)
	}
	raw[len(raw)/2] ^= 1
	if e = os.WriteFile(file, raw, 0600); e != nil {
		t.Fatal(e)
	}
	if e = p.View.Verify(); e == nil {
		t.Fatal("explicit full verification skipped the base")
	}
}
