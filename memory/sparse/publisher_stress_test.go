package sparse

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"
)

func TestPublisherSustainedConcurrentReaders(t *testing.T) {
	src, _, rs, a, pub, priv := authorizationFixture(t)
	if e := src.Publish(a.SourceView, ""); e != nil {
		t.Fatal(e)
	}
	path := filepath.Join(t.TempDir(), "approval")
	a.Records = a.Records[:1]
	a.ReferenceLookups = []ReferenceLookupPolicy{{"general", "test", "exact-key-v1"}}
	write := func() {
		raw, _ := json.Marshal(signedGrant(t, a, priv))
		if e := os.WriteFile(path+".next", raw, 0600); e != nil {
			t.Fatal(e)
		}
		if e := os.Rename(path+".next", path); e != nil {
			t.Fatal(e)
		}
	}
	write()
	p := Publisher{Source: src, Delivery: Delivery{filepath.Join(t.TempDir(), "delivery")}, ApprovalPath: path, PublicKey: pub, Subject: a.Subject, PolicyEpoch: a.PolicyEpoch, ReaderGID: -1}
	if out, e := p.Reconcile(testNow); e != nil || out.State != "installed" {
		t.Fatalf("%+v %v", out, e)
	}
	var stop atomic.Bool
	var reads atomic.Int64
	var failures atomic.Int64
	var wg sync.WaitGroup
	for range 16 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for !stop.Load() {
				reader, e := (Store{p.Delivery.Root}).PinPublished(nil)
				if e != nil {
					continue
				}
				result, e := reader.Recall("public astronomy", 4, "test", testNow)
				if e != nil || result.Outcome != "hit" {
					failures.Add(1)
				}
				reader.Close()
				reads.Add(1)
			}
		}()
	}
	defer func() { stop.Store(true); wg.Wait() }()
	for i := 1; i <= 50; i++ {
		row := rs[0]
		row.Revision = fmt.Sprintf("revision-%d", i)
		row.Content = fmt.Sprintf("public astronomy revision %d", i)
		old := a.SourceView
		a.SourceView = build(t, src, changes("general", "general", "", row))
		if e := src.Publish(a.SourceView, old); e != nil {
			t.Fatal(e)
		}
		a.Records = []AuthorizedRecord{AuthorizeRecord(row)}
		a.ID = row.Revision
		write()
		out, e := p.Reconcile(testNow)
		if e != nil || out.State != "installed" {
			t.Fatalf("iteration %d: %+v %v", i, out, e)
		}
		if i%10 == 0 {
			os.WriteFile(path, []byte("interrupted approval update"), 0600)
			out, e = p.Reconcile(testNow)
			if e != nil || out.State != "withdrawn" {
				t.Fatalf("%+v %v", out, e)
			}
			if _, e = (Store{p.Delivery.Root}).PinPublished(nil); e == nil {
				t.Fatal("withdrawn publication opened")
			}
			write()
			if out, e = p.Reconcile(testNow); e != nil || out.State != "installed" {
				t.Fatalf("%+v %v", out, e)
			}
		}
		// Simulate the abandoned private stage left by a killed install, then restart.
		abandoned := filepath.Join(p.Delivery.Root, "snapshots", ".stage-interrupted")
		if e = os.Mkdir(abandoned, 0700); e != nil {
			t.Fatal(e)
		}
		restarted := p
		out, e = restarted.Reconcile(testNow)
		if e != nil || out.State != "unchanged" {
			t.Fatalf("%+v %v", out, e)
		}
		if _, e = os.Stat(abandoned); !os.IsNotExist(e) {
			t.Fatal("abandoned stage retained")
		}
	}
	stop.Store(true)
	wg.Wait()
	if failures.Load() != 0 || reads.Load() == 0 {
		t.Fatalf("reads=%d failures=%d", reads.Load(), failures.Load())
	}
	t.Logf("50 replacements, 5 withdrawals/reinstalls, 50 restart recoveries, 16 readers: %d reads, %d failures", reads.Load(), failures.Load())
}
