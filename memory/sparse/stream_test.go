package sparse

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestStreamLiveRemovalDisconnectResumeAndDenial(t *testing.T) {
	one, id1 := deliveryFixture(t, true)
	two, id2 := deliveryFixture(t, false)
	var mu sync.Mutex
	selected := one
	allowed := true
	calls := 0
	server := httptest.NewServer(PublicationStreamHandler(func(r *http.Request) (Store, error) {
		mu.Lock()
		defer mu.Unlock()
		calls++
		if !allowed {
			return Store{}, errors.New("denied")
		}
		return selected, nil
	}, 10*time.Millisecond))
	defer server.Close()
	d := Delivery{filepath.Join(t.TempDir(), "delivery")}
	state := Store{filepath.Join(t.TempDir(), "private")}
	run := func() (context.CancelFunc, <-chan error, <-chan PublicationResult) {
		ctx, cancel := context.WithCancel(context.Background())
		done := make(chan error, 1)
		commits := make(chan PublicationResult, 8)
		request, _ := http.NewRequest("GET", server.URL, nil)
		go func() {
			done <- FollowPublication(ctx, server.Client(), request, state, d, -1, 1<<20, func(r PublicationResult) { commits <- r })
		}()
		return cancel, done, commits
	}
	receive := func(ch <-chan PublicationResult, id string) {
		t.Helper()
		select {
		case r := <-ch:
			if r.View != id {
				t.Fatalf("wrong commit: %+v", r)
			}
		case <-time.After(5 * time.Second):
			t.Fatal("no commit")
		}
	}
	cancel, done, commits := run()
	receive(commits, id1)
	mu.Lock()
	selected = two
	mu.Unlock()
	receive(commits, id2)
	cancel()
	select {
	case e := <-done:
		if e == nil {
			t.Fatal("disconnect accepted")
		}
	case <-time.After(5 * time.Second):
		t.Fatal("disconnect stalled")
	}
	if _, e := (Store{d.Root}).PinPublished(nil); e == nil {
		t.Fatal("disconnected delivery visible")
	}
	// Same committed private cursor restores public delivery from a heartbeat;
	// unchanged records need not be retransmitted after a disconnect.
	cancel, done, commits = run()
	defer cancel()
	receive(commits, id2)
	mu.Lock()
	allowed = false
	mu.Unlock()
	select {
	case e := <-done:
		if e == nil {
			t.Fatal("denial accepted")
		}
	case <-time.After(5 * time.Second):
		t.Fatal("denial stalled")
	}
	if _, e := (Store{d.Root}).PinPublished(nil); e == nil {
		t.Fatal("denied delivery visible")
	}
	mu.Lock()
	n := calls
	mu.Unlock()
	if n < 4 {
		t.Fatal("authorization was not rechecked")
	}
}
func TestRetentionRequiresCurrentCanonicalHash(t *testing.T) {
	one, id := deliveryFixture(t, true)
	p, e := one.OpenPublished(id)
	if e != nil {
		t.Fatal(e)
	}
	defer p.Close()
	var proofs []RetentionProof
	for _, loc := range p.View.records {
		r, e := p.View.read(loc)
		if e != nil {
			t.Fatal(e)
		}
		proofs = append(proofs, RetentionProof{r.Ref, AuthorizeRecord(r).SHA256})
	}
	for _, ok := range p.Retain(proofs, testNow) {
		if !ok {
			t.Fatal("unchanged record lost")
		}
	}
	proofs[0].Hash = digest([]byte("changed"))
	if p.Retain(proofs, testNow)[0] {
		t.Fatal("wrong payload hash retained")
	}
	proofs[0].Ref.Revision = "wrong"
	if p.Retain(proofs, testNow)[0] {
		t.Fatal("wrong revision retained")
	}
}

func TestPublishedRemoteGuardChecksReceiptAndCanonicalRevision(t *testing.T) {
	base, baseID := deliveryFixture(t, false)
	src := Store{filepath.Join(t.TempDir(), "source")}
	row := Record{Ref: Ref{"personal", "5", "one"}, Scope: Scope{"user", "_user"}, Key: "drink", Content: "oolong", Kind: "preference", Tier: "semantic", Confidence: 1, Lifecycle: "active"}
	id, e := src.CompileReleased(base, baseID, digest([]byte("release")), "personal", "test", []Record{row}, nil, testNow)
	if e != nil {
		t.Fatal(e)
	}
	p, e := src.OpenPublished(id)
	if e != nil {
		t.Fatal(e)
	}
	defer p.Close()
	restriction, e := p.RestrictRemote("personal")
	if e != nil || len(restriction.IDs) != 1 || restriction.IDs[0] != 5 {
		t.Fatalf("%+v %v", restriction, e)
	}
	body := map[string]any{"status": "ok", "facts": []map[string]any{{"id": 5, "content": "oolong"}}, "restriction": restriction}
	raw, _ := json.Marshal(body)
	refs, e := p.ResolveRemote(raw, testNow)
	if e != nil || len(refs) != 1 || refs[0] != row.Ref {
		t.Fatalf("%+v %v", refs, e)
	}
	for _, facts := range [][]map[string]any{{{"id": 5, "content": "stale"}}, {{"id": 6, "content": "canary"}}} {
		body["facts"] = facts
		raw, _ = json.Marshal(body)
		if _, e = p.ResolveRemote(raw, testNow); e == nil {
			t.Fatal("unreleased payload accepted")
		}
	}
	body["facts"] = []any{}
	raw, _ = json.Marshal(body)
	if _, e = p.ResolveRemote(raw, testNow); e != nil {
		t.Fatal("restricted miss rejected", e)
	}
	delete(body, "restriction")
	raw, _ = json.Marshal(body)
	if _, e = p.ResolveRemote(raw, testNow); e == nil {
		t.Fatal("unrestricted response accepted")
	}
}

func TestMalformedStreamWithdrawsWithoutAdvancingPrivateCursor(t *testing.T) {
	one, id := deliveryFixture(t, true)
	for name, body := range map[string]string{
		"truncated":       `{"version":1,"state":"delta"`,
		"version":         `{"version":2,"state":"unchanged"}` + "\n",
		"wrong-heartbeat": `{"version":1,"state":"unchanged","view":"wrong"}` + "\n",
		"oversize":        strings.Repeat("x", 2048) + "\n",
		"unknown-field":   `{"version":1,"state":"withdrawn","unexpected":true}` + "\n",
	} {
		t.Run(name, func(t *testing.T) {
			state := Store{filepath.Join(t.TempDir(), "private")}
			os.MkdirAll(state.Root, 0700)
			mirror := Delivery{filepath.Join(state.Root, "committed")}
			d := Delivery{filepath.Join(t.TempDir(), "public")}
			if _, e := mirror.Install(one, "", -1); e != nil {
				t.Fatal(e)
			}
			if _, e := d.Install(one, "", -1); e != nil {
				t.Fatal(e)
			}
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Header.Get("Last-Event-ID") != id {
					t.Error("resume cursor missing")
				}
				io.WriteString(w, body)
			}))
			defer server.Close()
			req, _ := http.NewRequest("GET", server.URL, nil)
			if e := FollowPublication(context.Background(), server.Client(), req, state, d, -1, 1024, nil); e == nil {
				t.Fatal("bad stream accepted")
			}
			if current, _ := d.current(); current != "" {
				t.Fatal("bad stream left public delivery accessible")
			}
			if current, _ := mirror.current(); current != id {
				t.Fatal("bad stream corrupted last good cursor")
			}
		})
	}
}

func TestStreamRevocationDuringStagingNeverExposesQueuedImage(t *testing.T) {
	src, _ := deliveryFixture(t, true)
	server := httptest.NewServer(PublicationStreamHandler(func(r *http.Request) (Store, error) {
		if r.Method == "HEAD" {
			return Store{}, errors.New("release revoked during staging")
		}
		return src, nil
	}, time.Second))
	defer server.Close()
	d := Delivery{filepath.Join(t.TempDir(), "public")}
	state := Store{filepath.Join(t.TempDir(), "private")}
	req, _ := http.NewRequest("GET", server.URL, nil)
	if e := FollowPublication(context.Background(), server.Client(), req, state, d, -1, 1<<20, nil); e == nil || !strings.Contains(e.Error(), "at commit") {
		t.Fatalf("queued image released: %v", e)
	}
	if id, _ := d.current(); id != "" {
		t.Fatal("revoked bytes exposed")
	}
	entries, e := os.ReadDir(filepath.Join(d.Root, "snapshots"))
	if e != nil || len(entries) != 0 {
		t.Fatal("unreleased staging bytes retained", e)
	}
}
