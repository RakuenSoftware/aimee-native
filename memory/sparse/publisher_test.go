package sparse

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestPublisherReconcilesApprovalChangesAndWithdrawal(t *testing.T) {
	src, _, _, a, pub, priv := authorizationFixture(t)
	if err := src.Publish(a.SourceView, ""); err != nil {
		t.Fatal(err)
	}
	a.ReferenceLookups = []ReferenceLookupPolicy{{"general", "test", "exact-key-v1"}}
	approval := filepath.Join(t.TempDir(), "approval")
	write := func() {
		t.Helper()
		raw, _ := json.Marshal(signedGrant(t, a, priv))
		if err := os.WriteFile(approval, raw, 0600); err != nil {
			t.Fatal(err)
		}
	}
	write()
	p := Publisher{Source: src, Delivery: Delivery{filepath.Join(t.TempDir(), "recipient")}, ApprovalPath: approval, PublicKey: pub, Subject: a.Subject, PolicyEpoch: a.PolicyEpoch, ReaderGID: -1}
	first, e := p.Reconcile(testNow)
	if e != nil || first.State != "installed" {
		t.Fatalf("%+v %v", first, e)
	}
	// Restart requires no in-memory publisher state.
	same, e := p.Reconcile(testNow)
	if e != nil || same.State != "unchanged" {
		t.Fatalf("%+v %v", same, e)
	}
	a.ID = "replacement"
	a.Records = a.Records[:1]
	write()
	next, e := p.Reconcile(testNow)
	if e != nil || next.State != "installed" || next.View == first.View {
		t.Fatalf("%+v %v", next, e)
	}
	if _, e = os.Stat(filepath.Join(p.Delivery.Root, "snapshots", first.View)); !os.IsNotExist(e) {
		t.Fatal("old payload retained")
	}
	// Expiration is enforced by the publisher, not local read identity checks.
	a.ValidUntil = testNow.Add(-time.Second).Format(time.RFC3339)
	write()
	out, e := p.Reconcile(testNow)
	if e != nil || out.State != "withdrawn" {
		t.Fatalf("%+v %v", out, e)
	}
	if _, e = (Store{p.Delivery.Root}).PinPublished(nil); e == nil {
		t.Fatal("withdrawn image readable")
	}
	a.ValidUntil = testNow.Add(time.Hour).Format(time.RFC3339)
	write()
	if out, e = p.Reconcile(testNow); e != nil || out.State != "installed" {
		t.Fatalf("%+v %v", out, e)
	}
	os.WriteFile(approval, []byte("partial write"), 0600)
	if out, e = p.Reconcile(testNow); e != nil || out.State != "withdrawn" {
		t.Fatalf("%+v %v", out, e)
	}
	write()
	if _, e = p.Reconcile(testNow); e != nil {
		t.Fatal(e)
	}
	os.Remove(filepath.Join(src.Root, "CURRENT"))
	if out, e = p.Reconcile(testNow); e != nil || out.Reason != "source_approval_mismatch" {
		t.Fatalf("%+v %v", out, e)
	}
}
