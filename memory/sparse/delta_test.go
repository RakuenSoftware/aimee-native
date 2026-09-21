package sparse

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestRecipientDeltaReplacementRemovalReplayAndIntegrity(t *testing.T) {
	one, id1 := deliveryFixture(t, true)
	two, id2 := deliveryFixture(t, false)
	a, e := one.OpenPublished(id1)
	if e != nil {
		t.Fatal(e)
	}
	defer a.Close()
	b, e := two.OpenPublished(id2)
	if e != nil {
		t.Fatal(e)
	}
	defer b.Close()
	delta, e := DiffPublished(a, b)
	if e != nil {
		t.Fatal(e)
	}
	for _, l := range delta.Layers {
		if len(l.Upsert) != 0 {
			t.Fatal("unchanged records retransmitted")
		}
	}
	d := Delivery{filepath.Join(t.TempDir(), "recipient")}
	if _, e = d.Install(one, "", -1); e != nil {
		t.Fatal(e)
	}
	bad := delta
	bad.Base = digest([]byte("wrong"))
	if _, e = d.ApplyDelta(bad, -1); e == nil {
		t.Fatal("gap accepted")
	}
	bad = delta
	bad.Target = digest([]byte("tampered"))
	if _, e = d.ApplyDelta(bad, -1); e == nil {
		t.Fatal("tampering accepted")
	}
	if current, _ := d.current(); current != id1 {
		t.Fatal("partial update visible")
	}
	if r, e := d.ApplyDelta(delta, -1); e != nil || r.View != id2 {
		t.Fatalf("%+v %v", r, e)
	}
	if r, e := d.ApplyDelta(delta, -1); e != nil || r.State != "unchanged" {
		t.Fatalf("replay: %+v %v", r, e)
	}
	q, e := (Store{d.Root}).PinPublished(nil)
	if e != nil {
		t.Fatal(e)
	}
	defer q.Close()
	if len(q.View.records) != len(b.View.records) {
		t.Fatal("removal was not applied")
	}
	oldPath := filepath.Join(d.Root, "snapshots", id1)
	if _, e = os.Stat(oldPath); !os.IsNotExist(e) {
		t.Fatal("obsolete snapshot retained")
	}
	full, e := DiffPublished(nil, b)
	if e != nil {
		t.Fatal(e)
	}
	fresh := Delivery{filepath.Join(t.TempDir(), "recipient")}
	if _, e = fresh.ApplyDelta(full, -1); e != nil {
		t.Fatal(e)
	}
	raw, _ := json.Marshal(delta)
	initial, _ := json.Marshal(full)
	t.Logf("delta_bytes=%d bootstrap_bytes=%d", len(raw), len(initial))
}

func TestLiveDeltaOnlyTransmitsChangedRecordAndCue(t *testing.T) {
	base, baseID := deliveryFixture(t, false)
	source := Store{filepath.Join(t.TempDir(), "publisher")}
	a := Record{Ref: Ref{"personal", "5", "one"}, Scope: Scope{"user", "_user"}, Key: "preferred drink", Content: "unit-x prefers oolong", Kind: "preference", Tier: "semantic", Confidence: 1, Lifecycle: "active"}
	b := a
	b.Ref = Ref{"personal", "6", "one"}
	b.Key = "home city"
	b.Content = "unit-y lives in Lima"
	cues := func(rows []Record) []ReferenceCue {
		out := []ReferenceCue{}
		for _, r := range rows {
			out = append(out, ReferenceCue{r.Ref, r.Key, "test"})
		}
		return out
	}
	rows := []Record{a, b}
	id1, e := source.CompileReleased(base, baseID, digest([]byte("release1")), "personal", "test", rows, cues(rows), testNow)
	if e != nil {
		t.Fatal(e)
	}
	one, e := source.OpenPublished(id1)
	if e != nil {
		t.Fatal(e)
	}
	defer one.Close()
	a.Revision = "two"
	a.Content = "unit-x prefers jasmine"
	rows = []Record{a, b}
	id2, e := source.CompileReleased(base, baseID, digest([]byte("release2")), "personal", "test", rows, cues(rows), testNow)
	if e != nil {
		t.Fatal(e)
	}
	two, e := source.OpenPublished(id2)
	if e != nil {
		t.Fatal(e)
	}
	defer two.Close()
	delta, e := DiffPublished(one, two)
	if e != nil {
		t.Fatal(e)
	}
	upserts := 0
	for _, layer := range delta.Layers {
		upserts += len(layer.Upsert)
	}
	if upserts != 1 || len(delta.Layers[1].CueInsert) != 1 || len(delta.Layers[1].CueRemove) != 1 || !delta.Layers[1].ReuseServing {
		t.Fatalf("nonincremental delta: %+v", delta)
	}
	raw, _ := json.Marshal(delta)
	if bytes.Contains(raw, []byte("oolong")) || bytes.Contains(raw, []byte("Lima")) {
		t.Fatal("unchanged/retired content retransmitted")
	}
	dst := Store{filepath.Join(t.TempDir(), "reconstructed")}
	if e = MaterializeDelta(source, dst, delta); e != nil {
		t.Fatal(e)
	}
	if id, _ := dst.Current(); id != id2 {
		t.Fatal("wrong reconstructed view")
	}
	if got := two.Retain([]RetentionProof{{b.Ref, AuthorizeRecord(b).SHA256}, {Ref{"personal", "5", "one"}, AuthorizeRecord(rows[0]).SHA256}}, testNow); !got[0] || got[1] {
		t.Fatalf("retention %+v", got)
	}
	bad := delta
	bad.Layers = append([]RecordDelta{}, delta.Layers...)
	bad.Layers[1].Upsert = nil
	if e = MaterializeDelta(source, Store{filepath.Join(t.TempDir(), "bad")}, bad); e == nil {
		t.Fatal("partial transaction accepted")
	}
	// A routing-only update must not transmit records or invalidate values.
	aliases := cues(rows)
	aliases = append(aliases, ReferenceCue{a.Ref, "usual beverage", "test"})
	cueID, e := source.CompileReleased(base, baseID, digest([]byte("cue-only")), "personal", "test", rows, aliases, testNow)
	if e != nil {
		t.Fatal(e)
	}
	cueView, e := source.OpenPublished(cueID)
	if e != nil {
		t.Fatal(e)
	}
	defer cueView.Close()
	cueDelta, e := DiffPublished(two, cueView)
	if e != nil {
		t.Fatal(e)
	}
	for _, layer := range cueDelta.Layers {
		if len(layer.Upsert)+len(layer.Remove) != 0 {
			t.Fatal("cue-only update retransmitted records")
		}
	}
	if len(cueDelta.Layers[1].CueInsert) != 1 {
		t.Fatal("missing new alias")
	}
	if e = MaterializeDelta(source, Store{filepath.Join(t.TempDir(), "cue-only")}, cueDelta); e != nil {
		t.Fatal(e)
	}
	for _, ok := range cueView.Retain([]RetentionProof{{a.Ref, AuthorizeRecord(a).SHA256}, {b.Ref, AuthorizeRecord(b).SHA256}}, testNow) {
		if !ok {
			t.Fatal("cue edit invalidated record")
		}
	}
	// Neither a deduplicated/retired object nor its cue survives the new view.
	id3, e := source.CompileReleased(base, baseID, digest([]byte("release3")), "personal", "test", []Record{b}, cues([]Record{b}), testNow)
	if e != nil {
		t.Fatal(e)
	}
	three, e := source.OpenPublished(id3)
	if e != nil {
		t.Fatal(e)
	}
	defer three.Close()
	retired, e := DiffPublished(two, three)
	if e != nil {
		t.Fatal(e)
	}
	if len(retired.Layers[1].Remove) != 1 || len(retired.Layers[1].Upsert) != 0 {
		t.Fatal("retirement did not become a removal")
	}
	if e = MaterializeDelta(source, Store{filepath.Join(t.TempDir(), "retired")}, retired); e != nil {
		t.Fatal(e)
	}
}
