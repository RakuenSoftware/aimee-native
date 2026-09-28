package nativepublication

import (
	"context"
	"encoding/hex"
	"encoding/json"
	policy "github.com/JBailes/aimee/server-go/modules/execution-policy"
	"net/http"
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

func TestAuthoritySelectsOnlyApprovedModelsWithinCurrentRecipient(t *testing.T) {
	dir := t.TempDir()
	release := policy.MemoryReleasePolicy{Version: 1, Recipient: "alice", PeerUID: uint32(os.Geteuid()), Namespace: "personal", BaseView: strings.Repeat("a", 64), ValidUntil: time.Now().Add(time.Hour).Format(time.RFC3339Nano), Active: true}
	write := func(path string, value any) {
		t.Helper()
		raw, err := json.Marshal(value)
		if err != nil {
			t.Fatal(err)
		}
		if err = os.WriteFile(path, raw, 0600); err != nil {
			t.Fatal(err)
		}
	}
	rp := filepath.Join(dir, "release.json")
	write(rp, release)
	first := Preparer{Binary: "/private/prepare", Template: "/private/first.json", Profile: Profile{Schema: 1, Recipient: "alice", Model: "first", ModelConfigSHA256: strings.Repeat("b", 64)}}
	second := Preparer{Binary: "/private/prepare", Template: "/private/second.json", Profile: Profile{Schema: 1, Recipient: "alice", Model: "second", ModelConfigSHA256: strings.Repeat("c", 64)}}
	registry := bindingFile{Schema: 1, Bindings: []Binding{{Principal: "webuser:alice", ReleasePolicy: rp, PublisherUID: release.PeerUID, Preparer: first, Models: map[string]Preparer{"second": second}}}}
	path := filepath.Join(dir, "bindings.json")
	write(path, registry)
	authority := Authority{Bindings: path, FrontendUID: uint32(os.Geteuid())}
	request := func(query string) *http.Request {
		r := httptest.NewRequest("GET", "/v1/native/bootstrap"+query, nil)
		r.Header.Set("X-Aimee-Native-Principal", hex.EncodeToString([]byte("webuser:alice")))
		return r.WithContext(context.WithValue(r.Context(), peerKey{}, authority.FrontendUID))
	}
	legacy, err := authority.Resolve(request(""))
	if err != nil {
		t.Fatal(err)
	}
	selected, err := authority.Resolve(request("?model=second"))
	if err != nil {
		t.Fatal(err)
	}
	if selected.Profile.Model != "second" || selected.Recipient != "alice" || selected.Scope == legacy.Scope {
		t.Fatal("selection lost profile or authorization isolation")
	}
	explicit, err := authority.Resolve(request("?model=first"))
	if err != nil || explicit.Scope != legacy.Scope {
		t.Fatal("default selection changed legacy scope", err)
	}
	for _, query := range []string{"?model=unknown", "?model=", "?model=second&model=first", "?recipient=bob", "?model=second&recipient=bob", "?model=%zz"} {
		if _, err := authority.Resolve(request(query)); err == nil {
			t.Fatalf("accepted unapproved or ambiguous selector %q", query)
		}
	}
	if selected.Check(request("?model=first"), Prepared{}) == nil {
		t.Fatal("alternate-model capability accepted under the default route")
	}
	changed := second
	changed.Template = "/private/revised.json"
	registry.Bindings[0].Models["second"] = changed
	write(path, registry)
	revised, err := authority.Resolve(request("?model=second"))
	if err != nil || revised.Scope == selected.Scope {
		t.Fatal("profile update did not revoke prior scope", err)
	}
	if selected.Check(request("?model=second"), Prepared{}) == nil {
		t.Fatal("stale route capability survived template change")
	}
	changed.Profile.Recipient = "bob"
	registry.Bindings[0].Models["second"] = changed
	write(path, registry)
	if _, err := authority.Resolve(request("?model=second")); err == nil {
		t.Fatal("model map widened recipient authority")
	}
	registry.Bindings[0].Models["second"] = second
	write(path, registry)
	release.Active = false
	write(rp, release)
	if _, err := authority.Resolve(request("?model=second")); err == nil {
		t.Fatal("alternate model bypassed release withdrawal")
	}
}
