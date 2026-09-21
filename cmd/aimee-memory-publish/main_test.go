package main

import (
	"context"
	"encoding/json"
	policy "github.com/JBailes/aimee/server-go/modules/execution-policy"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func testRelease() policy.MemoryReleasePolicy {
	return policy.MemoryReleasePolicy{Version: 1, Recipient: "test", PeerUID: uint32(os.Geteuid()), Namespace: "personal", BaseView: strings.Repeat("a", 64), ValidUntil: time.Now().Add(time.Hour).UTC().Format(time.RFC3339Nano), Active: true}
}
func TestPolicyFileRejectsSymlinkPermissionsAndTrailingJSON(t *testing.T) {
	p := filepath.Join(t.TempDir(), "policy")
	raw, _ := json.Marshal(testRelease())
	os.WriteFile(p, raw, 0600)
	if _, _, e := readPolicy(p); e != nil {
		t.Fatal(e)
	}
	link := p + ".link"
	os.Symlink(p, link)
	if _, _, e := readPolicy(link); e == nil {
		t.Fatal("symlink accepted")
	}
	os.Chmod(p, 0666)
	if _, _, e := readPolicy(p); e == nil {
		t.Fatal("writable policy accepted")
	}
	os.Chmod(p, 0600)
	os.WriteFile(p, append(raw, []byte("{}")...), 0600)
	if _, _, e := readPolicy(p); e == nil {
		t.Fatal("trailing document accepted")
	}
}
func TestPolicyChangeWithdrawsBeforeSourceAccess(t *testing.T) {
	path := filepath.Join(t.TempDir(), "policy")
	release := testRelease()
	raw, _ := json.Marshal(release)
	os.WriteFile(path, raw, 0600)
	p := publisher{policyPath: path, recipient: "test", lastRelease: "old", dsn: "INVALID"}
	r := httptest.NewRequest("GET", "http://local/", nil)
	if _, e := p.resolve(r); e == nil || !strings.Contains(e.Error(), "authenticated") {
		t.Fatalf("unauthenticated: %v", e)
	}
	r = r.WithContext(context.WithValue(r.Context(), uidKey{}, uint32(os.Geteuid())))
	if _, e := p.resolve(r); e == nil || !strings.Contains(e.Error(), "withdraw before") {
		t.Fatalf("missing withdrawal barrier: %v", e)
	}
	if p.lastRelease != release.Digest() {
		t.Fatal("barrier did not remember policy")
	}
}
