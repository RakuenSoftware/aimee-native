package nativepublication

import (
	"context"
	"encoding/hex"
	"encoding/json"
	policy "github.com/JBailes/aimee/server-go/modules/execution-policy"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestAuthorityRequiresKernelPeerAndCurrentExplicitRelease(t *testing.T) {
	dir := t.TempDir()
	release := policy.MemoryReleasePolicy{Version: 1, Recipient: "alice", PeerUID: uint32(os.Geteuid()), Namespace: "personal", BaseView: strings.Repeat("a", 64), ValidUntil: time.Now().Add(time.Hour).Format(time.RFC3339Nano), Active: true}
	rp := filepath.Join(dir, "release.json")
	write := func(path string, v any) {
		t.Helper()
		b, e := json.Marshal(v)
		if e != nil {
			t.Fatal(e)
		}
		if e = os.WriteFile(path, b, 0600); e != nil {
			t.Fatal(e)
		}
	}
	write(rp, release)
	b := Binding{Principal: "webuser:alice", ReleasePolicy: rp, PublisherUID: release.PeerUID, Preparer: Preparer{Binary: "/private/native-prepare", Template: "/private/alice.json", Profile: Profile{Schema: 1, Recipient: "alice", Model: "model", ModelConfigSHA256: strings.Repeat("b", 64)}}}
	registry := bindingFile{Schema: 1, Bindings: []Binding{b}}
	ap := filepath.Join(dir, "bindings.json")
	write(ap, registry)
	a := Authority{Bindings: ap, FrontendUID: uint32(os.Geteuid())}
	r := httptest.NewRequest("GET", "/v1/native/bootstrap", nil)
	r.Header.Set("X-Aimee-Native-Principal", hex.EncodeToString([]byte(b.Principal)))
	if _, e := a.Resolve(r); e == nil {
		t.Fatal("network header accepted without kernel identity")
	}
	r = r.WithContext(context.WithValue(r.Context(), peerKey{}, a.FrontendUID+1))
	if _, e := a.Resolve(r); e == nil {
		t.Fatal("wrong Unix uid accepted")
	}
	r = r.WithContext(context.WithValue(r.Context(), peerKey{}, a.FrontendUID))
	original, e := a.Resolve(r)
	if e != nil {
		t.Fatal(e)
	}
	if original.Recipient != "alice" {
		t.Fatal(original.Recipient)
	}
	registry.Bindings[0].Preparer.Profile.Model = "other-model"
	write(ap, registry)
	changed, e := a.Resolve(r)
	if e != nil || changed.Scope == original.Scope {
		t.Fatal("model change retained lease scope", e)
	}
	registry.Bindings[0] = b
	write(ap, registry)
	r.Header.Add("X-Aimee-Native-Principal", hex.EncodeToString([]byte(b.Principal)))
	if _, e := a.Resolve(r); e == nil {
		t.Fatal("duplicate identity accepted")
	}
	r.Header.Set("X-Aimee-Native-Principal", hex.EncodeToString([]byte("webuser:bob")))
	if _, e := a.Resolve(r); e == nil {
		t.Fatal("unbound principal accepted")
	}
	r.Header.Set("X-Aimee-Native-Principal", hex.EncodeToString([]byte(b.Principal)))
	release.Active = false
	write(rp, release)
	if _, e := a.Resolve(r); e == nil {
		t.Fatal("revoked policy accepted")
	}
	release.Active = true
	release.ValidUntil = time.Now().Add(-time.Second).Format(time.RFC3339Nano)
	write(rp, release)
	if _, e := a.Resolve(r); e == nil {
		t.Fatal("expired policy accepted")
	}
	release.ValidUntil = time.Now().Add(time.Hour).Format(time.RFC3339Nano)
	release.Recipient = "bob"
	write(rp, release)
	if _, e := a.Resolve(r); e == nil {
		t.Fatal("wrong recipient accepted")
	}
	release.Recipient = "alice"
	write(rp, release)
	if e = os.Chmod(rp, 0666); e != nil {
		t.Fatal(e)
	}
	if _, e := a.Resolve(r); e == nil {
		t.Fatal("writable policy accepted")
	}
	if e = os.Remove(rp); e != nil {
		t.Fatal(e)
	}
	if _, e := a.Resolve(r); e == nil {
		t.Fatal("removed policy accepted")
	}
}
