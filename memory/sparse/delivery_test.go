package sparse

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
)

func deliveryFixture(t *testing.T, retainPrivate bool) (Store, string) {
	t.Helper()
	src, _, _, a, pub, priv := authorizationFixture(t)
	a.ReferenceLookups = []ReferenceLookupPolicy{{"general", "test", "exact-key-v1"}}
	if !retainPrivate {
		a.Records = a.Records[:1]
	}
	dst := Store{filepath.Join(t.TempDir(), "compiled")}
	id, err := src.CompileAuthorized(dst, signedGrant(t, a, priv), pub, a.Subject, a.PolicyEpoch, testNow)
	if err != nil {
		t.Fatal(err)
	}
	return dst, id
}

func TestDeliveryInstallReplaceWithdrawAndPhysicalCleanup(t *testing.T) {
	one, id1 := deliveryFixture(t, true)
	two, id2 := deliveryFixture(t, false)
	// Unreachable bytes in the publisher directory must not be delivered.
	if err := os.WriteFile(filepath.Join(one.Root, "objects", digest([]byte("FORBIDDEN_EXTRA"))), []byte("FORBIDDEN_EXTRA"), 0600); err != nil {
		t.Fatal(err)
	}
	d := Delivery{filepath.Join(t.TempDir(), "recipient")}
	if _, err := d.Install(one, "", -1); err != nil {
		t.Fatal(err)
	}
	p, err := (Store{d.Root}).PinPublished(nil)
	if err != nil {
		t.Fatal(err)
	}
	defer p.Close()
	if p.View.ID != id1 {
		t.Fatal("wrong initial generation")
	}
	result, err := d.Install(two, id1, -1)
	if err != nil {
		t.Fatal(err)
	}
	if result.View != id2 || result.RemovedSnapshots != 1 {
		t.Fatalf("%+v", result)
	}
	if _, err = os.Stat(filepath.Join(d.Root, "snapshots", id1)); !os.IsNotExist(err) {
		t.Fatal("old snapshot retained")
	}
	// Unlinking old files preserves an already-open request until it releases.
	if r, e := p.Recall("public astronomy", 4, "test", testNow); e != nil || r.Outcome != "hit" {
		t.Fatalf("pinned read lost: %+v %v", r, e)
	}
	q, err := (Store{d.Root}).PinPublished(p)
	if err != nil {
		t.Fatal(err)
	}
	defer q.Close()
	if q.View.ID != id2 {
		t.Fatal("next request missed update")
	}
	if err := filepath.WalkDir(d.Root, func(path string, e os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if e.IsDir() {
			return nil
		}
		b, err := os.ReadFile(path)
		for _, secret := range []string{"FORBIDDEN_EXTRA", "authorized alpha configuration", "CANARY_"} {
			if strings.Contains(string(b), secret) {
				t.Errorf("retired/withheld bytes remain at %s", path)
			}
		}
		return err
	}); err != nil {
		t.Fatal(err)
	}
	if _, err = d.Withdraw(id1); err == nil {
		t.Fatal("stale withdrawal accepted")
	}
	if _, err = d.Withdraw(id2); err != nil {
		t.Fatal(err)
	}
	if _, err = (Store{d.Root}).PinPublished(q); err == nil {
		t.Fatal("withdrawn publication pinned")
	}
	entries, err := os.ReadDir(filepath.Join(d.Root, "snapshots"))
	if err != nil || len(entries) != 0 {
		t.Fatal("withdrawn payload files retained")
	}
}

func TestDeliveryFailedInputAndConflictLeaveCurrentUntouched(t *testing.T) {
	one, id1 := deliveryFixture(t, true)
	two, _ := deliveryFixture(t, false)
	d := Delivery{filepath.Join(t.TempDir(), "recipient")}
	if _, err := d.Install(one, "", -1); err != nil {
		t.Fatal(err)
	}
	if _, err := d.Install(two, "", -1); err == nil {
		t.Fatal("stale publisher accepted")
	}
	id, _ := two.Current()
	v, err := two.OpenPublished(id)
	if err != nil {
		t.Fatal(err)
	}
	data := v.View.Layers[0].Data
	v.Close()
	if err = os.WriteFile(filepath.Join(two.Root, "objects", data), []byte("corrupt replacement"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err = d.Install(two, id1, -1); err == nil {
		t.Fatal("corrupt replacement installed")
	}
	current, err := d.current()
	if err != nil || current != id1 {
		t.Fatal("failed install changed publication")
	}
	// Simulate abandoned staging and an unreachable completed generation.
	for _, name := range []string{".stage-abandoned", strings.Repeat("a", 64)} {
		if err = os.Mkdir(filepath.Join(d.Root, "snapshots", name), 0700); err != nil {
			t.Fatal(err)
		}
	}
	if count, err := d.Prune(id1); err != nil || count != 2 {
		t.Fatalf("recovery: %d %v", count, err)
	}
	if current, _ = d.current(); current != id1 {
		t.Fatal("recovery deleted active generation")
	}
	raw, rawHead, _, _, _, _ := authorizationFixture(t)
	if err = raw.Publish(rawHead, ""); err != nil {
		t.Fatal(err)
	}
	if _, err = d.Install(raw, id1, -1); err == nil {
		t.Fatal("raw source delivered")
	}
}

func TestDeliveryConcurrentPinsAndReplacements(t *testing.T) {
	one, id1 := deliveryFixture(t, true)
	two, id2 := deliveryFixture(t, false)
	d := Delivery{filepath.Join(t.TempDir(), "recipient")}
	if _, err := d.Install(one, "", -1); err != nil {
		t.Fatal(err)
	}
	var wg sync.WaitGroup
	errors := make(chan error, 100)
	for range 4 {
		wg.Go(func() {
			var p *PublishedReader
			defer func() {
				if p != nil {
					p.Close()
				}
			}()
			for range 30 {
				next, err := (Store{d.Root}).PinPublished(p)
				if err != nil {
					errors <- err
					return
				}
				if p != nil && p != next {
					p.Close()
				}
				p = next
				if _, err = p.Recall("public astronomy", 4, "test", testNow); err != nil {
					errors <- err
					return
				}
			}
		})
	}
	for i := range 10 {
		src, expected := two, id1
		if i%2 == 1 {
			src, expected = one, id2
		}
		if _, err := d.Install(src, expected, -1); err != nil {
			errors <- err
		}
	}
	wg.Wait()
	close(errors)
	for err := range errors {
		t.Error(err)
	}
}

func TestDeliveryRevalidatesBeforeCommit(t *testing.T) {
	one, id := deliveryFixture(t, true)
	two, _ := deliveryFixture(t, false)
	d := Delivery{filepath.Join(t.TempDir(), "recipient")}
	if _, e := d.Install(one, "", -1); e != nil {
		t.Fatal(e)
	}
	called := false
	_, e := d.install(two, id, -1, func() error { called = true; return fmt.Errorf("upstream approval withdrawn during copy") })
	if e == nil || !called {
		t.Fatal("commit validation was bypassed")
	}
	head, e := (Store{d.Root}).Current()
	if e != nil || head != id {
		t.Fatal("unapproved replacement published")
	}
	entries, e := os.ReadDir(filepath.Join(d.Root, "snapshots"))
	if e != nil || len(entries) != 1 {
		t.Fatal("rejected stage retained")
	}
}
