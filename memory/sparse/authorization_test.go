package sparse

import (
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func authorizationFixture(t *testing.T) (Store, string, []Record, Authorization, ed25519.PublicKey, ed25519.PrivateKey) {
	t.Helper()
	s := Store{t.TempDir()}
	public := record("general", "1", "public astronomy")
	hiddenGlobal := record("general", "2", "CANARY_UNAPPROVED_GLOBAL")
	g := build(t, s, changes("general", "general", "", public, hiddenGlobal))
	alice := record("kb", "1", "authorized alpha configuration")
	alice.Scope = Scope{"project", "alpha"}
	alice.Metadata = json.RawMessage(`{"private_notes":"CANARY_OPAQUE_METADATA"}`)
	alice.Aliases = []string{"CANARY_PRIVATE_ALIAS"}
	bob := record("kb", "2", "CANARY_PROJECT_BETA")
	bob.Scope = Scope{"project", "beta"}
	alice.Edges = []Edge{{"CANARY_PRIVATE_RELATION", bob.Ref}}
	withheld := record("kb", "3", "CANARY_WITHHELD_SAME_SCOPE")
	withheld.Scope = alice.Scope
	old := record("kb", "4", "CANARY_DELETED_HISTORY")
	old.Scope = alice.Scope
	first := build(t, s, changes("kb", "kb", g, alice, bob, withheld, old))
	c := changes("kb", "kb", g)
	c.Previous = first
	c.Generation = 2
	c.Delete = []Ref{old.Ref}
	head := build(t, s, c)
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	a := Authorization{Version: 1, ID: "grant-alpha-1", Subject: "model-session-alpha", PolicyEpoch: "policy-1", SourceView: head, Active: true, ValidUntil: testNow.Add(time.Hour).Format(time.RFC3339), Grants: []string{"project:alpha"}, Records: []AuthorizedRecord{AuthorizeRecord(public), AuthorizeRecord(alice)}}
	return s, head, []Record{public, alice, bob}, a, pub, priv
}
func signedGrant(t *testing.T, a Authorization, key ed25519.PrivateKey) SignedAuthorization {
	t.Helper()
	s, e := SignAuthorization(a, key)
	if e != nil {
		t.Fatal(e)
	}
	return s
}
func TestAuthorizedSnapshotContainsOnlyApprovedPhysicalBytes(t *testing.T) {
	src, head, rs, a, pub, priv := authorizationFixture(t)
	signed := signedGrant(t, a, priv)
	dst := Store{filepath.Join(t.TempDir(), "model")}
	id, err := src.CompileAuthorized(dst, signed, pub, a.Subject, a.PolicyEpoch, testNow)
	if err != nil {
		t.Fatal(err)
	}
	v := open(t, dst, id)
	if err = v.CheckAuthorization(signed, pub, a.Subject, a.PolicyEpoch, testNow); err != nil {
		t.Fatal(err)
	}
	if len(v.records) != 2 {
		t.Fatal("wrong approved object count")
	}
	if _, err = v.Get(rs[2].Ref, map[string]bool{"project:beta": true}, testNow); err == nil {
		t.Fatal("forged query scope found excluded record")
	}
	if _, err = v.Get(rs[1].Ref, grantMap(a), testNow); err != nil {
		t.Fatal(err)
	}
	for _, m := range v.Layers {
		if m.Previous != "" {
			t.Fatal("history retained")
		}
	}
	err = filepath.WalkDir(dst.Root, func(p string, d os.DirEntry, e error) error {
		if e != nil {
			return e
		}
		if !d.IsDir() {
			b, e := os.ReadFile(p)
			if e != nil {
				return e
			}
			if bytes.Contains(b, []byte("CANARY_")) {
				t.Errorf("excluded bytes in %s", p)
			}
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	var archive bytes.Buffer
	if err = dst.Export(id, &archive); err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(archive.Bytes(), []byte("CANARY_")) {
		t.Fatal("model archive leaks excluded data")
	}
	var raw bytes.Buffer
	if err = src.Export(head, &raw); err != nil {
		t.Fatal(err)
	}
	if !bytes.Contains(raw.Bytes(), []byte("CANARY_DELETED_HISTORY")) {
		t.Fatal("test did not exercise unsafe history export")
	}
}
func TestAuthorizationDoesNotFollowModelClaims(t *testing.T) {
	_, _, _, a, pub, priv := authorizationFixture(t)
	signed := signedGrant(t, a, priv)
	cases := []struct {
		name, subject, epoch string
		now                  time.Time
		s                    SignedAuthorization
		key                  ed25519.PublicKey
	}{
		{"wrong subject", "model-session-beta", a.PolicyEpoch, testNow, signed, pub},
		{"wrong epoch", a.Subject, "policy-2", testNow, signed, pub},
		{"expiry boundary", a.Subject, a.PolicyEpoch, testNow.Add(time.Hour), signed, pub},
		{"empty expected subject", "", a.PolicyEpoch, testNow, signed, pub},
		{"missing public key", a.Subject, a.PolicyEpoch, testNow, signed, nil},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if _, e := VerifyAuthorization(c.s, c.key, c.subject, c.epoch, c.now); e == nil {
				t.Fatal("unauthorized grant accepted")
			}
		})
	}
	t.Run("tampered approval", func(t *testing.T) {
		s := signed
		s.Grant = bytes.Replace(s.Grant, []byte("model-session-alpha"), []byte("model-session-beta"), 1)
		if _, e := VerifyAuthorization(s, pub, "model-session-beta", a.PolicyEpoch, testNow); e == nil {
			t.Fatal("forgery accepted")
		}
	})
	t.Run("revoked grant", func(t *testing.T) {
		b := a
		b.Active = false
		if _, e := VerifyAuthorization(signedGrant(t, b, priv), pub, a.Subject, a.PolicyEpoch, testNow); e == nil {
			t.Fatal("revocation ignored")
		}
	})
	t.Run("duplicate identity", func(t *testing.T) {
		b := a
		b.Records = append(append([]AuthorizedRecord{}, a.Records...), a.Records[0])
		if _, e := VerifyAuthorization(signedGrant(t, b, priv), pub, a.Subject, a.PolicyEpoch, testNow); e == nil {
			t.Fatal("duplicate approval accepted")
		}
	})
}
func TestAuthorizedCompilerFailsClosed(t *testing.T) {
	src, _, rs, a, pub, priv := authorizationFixture(t)
	for _, name := range []string{"missing scope", "wrong content hash", "stale source revision", "unapproved read decision"} {
		t.Run(name, func(t *testing.T) {
			b := a
			b.Records = append([]AuthorizedRecord{}, a.Records...)
			switch name {
			case "missing scope":
				b.Grants = nil
			case "wrong content hash":
				b.Records[1].SHA256 = strings.Repeat("0", 64)
			case "stale source revision":
				b.Records[1].Revision = "old"
			case "unapproved read decision":
				b.ReadDigests = []string{strings.Repeat("0", 64)}
			}
			dst := Store{filepath.Join(t.TempDir(), "model")}
			if _, e := src.CompileAuthorized(dst, signedGrant(t, b, priv), pub, b.Subject, b.PolicyEpoch, testNow); e == nil {
				t.Fatal("invalid release compiled")
			}
			if _, e := os.Stat(dst.Root); !os.IsNotExist(e) {
				t.Fatal("failed approval left model files")
			}
		})
	}
	t.Run("broad scope is not blanket export", func(t *testing.T) {
		b := a
		b.Grants = append(b.Grants, "project:beta")
		dst := Store{filepath.Join(t.TempDir(), "model")}
		id, e := src.CompileAuthorized(dst, signedGrant(t, b, priv), pub, b.Subject, b.PolicyEpoch, testNow)
		if e != nil {
			t.Fatal(e)
		}
		if _, e = open(t, dst, id).Get(rs[2].Ref, grantMap(b), testNow); e == nil {
			t.Fatal("scope label authorized unapproved object")
		}
	})
	t.Run("no destination reuse", func(t *testing.T) {
		dst := Store{t.TempDir()}
		sentinel := filepath.Join(dst.Root, "prior-secret")
		os.WriteFile(sentinel, []byte("keep"), 0600)
		if _, e := src.CompileAuthorized(dst, signedGrant(t, a, priv), pub, a.Subject, a.PolicyEpoch, testNow); e == nil {
			t.Fatal("reused directory")
		}
		if b, _ := os.ReadFile(sentinel); string(b) != "keep" {
			t.Fatal("deleted existing directory")
		}
	})
}
func TestFallbackCannotReturnUnapprovedOrRicherPayload(t *testing.T) {
	src, _, rs, a, pub, priv := authorizationFixture(t)
	dst := Store{filepath.Join(t.TempDir(), "model")}
	signed := signedGrant(t, a, priv)
	id, e := src.CompileAuthorized(dst, signed, pub, a.Subject, a.PolicyEpoch, testNow)
	if e != nil {
		t.Fatal(e)
	}
	v := open(t, dst, id)
	good := map[string]any{"status": "ok", "facts": []any{map[string]any{"id": "1", "content": rs[1].Content, "scope": rs[1].Scope}}, "windows": []any{}, "active_context_missing": false}
	raw, _ := json.Marshal(good)
	if e = v.AuthorizeResponse(raw, a, testNow); e != nil {
		t.Fatal(e)
	}
	for _, tc := range []struct{ name, raw string }{
		{"missing and unauthorized share unavailable outcome", `{"status":"ok","facts":[],"windows":[]}`},
		{"another project", `{"facts":[{"id":2,"content":"CANARY_PROJECT_BETA"}]}`},
		{"same ID changed content", `{"facts":[{"id":1,"content":"CANARY_CHANGED"}]}`},
		{"mixed approved and denied", `{"facts":[{"id":1,"content":"authorized alpha configuration"},{"id":2,"content":"CANARY_PROJECT_BETA"}]}`},
		{"hidden fact metadata", `{"facts":[{"id":1,"content":"authorized alpha configuration","notes":"CANARY"}]}`},
		{"hidden response metadata", `{"facts":[],"evidence":"CANARY"}`},
		{"episode payload", `{"facts":[],"windows":[{"content":"CANARY"}]}`},
		{"missing context", `{"facts":[],"active_context_missing":true}`},
		{"false success", `{"status":"error","facts":[]}`},
		{"foreign scope", `{"facts":[{"id":1,"content":"authorized alpha configuration","scope":{"type":"project","value":"beta"}}]}`},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if e = v.AuthorizeResponse(json.RawMessage(tc.raw), a, testNow); e == nil {
				t.Fatal("fallback exposed unsupported information")
			}
		})
	}
}
func TestSignedApprovalDoesNotBlessHiddenPhysicalData(t *testing.T) {
	src, _, _, a, pub, priv := authorizationFixture(t)
	signed := signedGrant(t, a, priv)
	for _, attack := range []string{"unindexed bytes", "unapproved index terms", "hidden manifest fields"} {
		t.Run(attack, func(t *testing.T) {
			dst := Store{filepath.Join(t.TempDir(), "model")}
			id, e := src.CompileAuthorized(dst, signed, pub, a.Subject, a.PolicyEpoch, testNow)
			if e != nil {
				t.Fatal(e)
			}
			m, e := dst.manifest(id)
			if e != nil {
				t.Fatal(e)
			}
			switch attack {
			case "unindexed bytes":
				b, _ := dst.read(m.Data)
				m.Data, e = dst.put(append(b, []byte("CANARY_HIDDEN_BYTES")...))
			case "unapproved index terms":
				b, _ := dst.read(m.Index)
				var idx Index
				json.Unmarshal(b, &idx)
				idx.Postings["CANARY_INDEX"] = []int{0}
				b, _ = json.Marshal(idx)
				m.Index, e = dst.put(b)
			}
			if e != nil {
				t.Fatal(e)
			}
			raw, _ := json.Marshal(m)
			if attack == "hidden manifest fields" {
				raw = append(raw[:len(raw)-1], []byte(`,"hidden":"CANARY_MANIFEST"}`)...)
			}
			forged, e := dst.put(raw)
			if e != nil {
				t.Fatal(e)
			}
			v, e := dst.Open(forged)
			if e != nil {
				return
			}
			defer v.Close()
			if e = v.CheckAuthorization(signed, pub, a.Subject, a.PolicyEpoch, testNow); e == nil {
				t.Fatal("hidden contents accepted")
			}
		})
	}
}

func TestThousandRecordsTenIndependentAuthorizations(t *testing.T) {
	src := Store{t.TempDir()}
	records := []Record{}
	for i := 0; i < 1000; i++ {
		records = append(records, record("general", fmt.Sprintf("%04d", i), fmt.Sprintf("PRIVATE_OBJECT_%04d_VALUE", i)))
	}
	head := build(t, src, changes("general", "general", "", records...))
	pub, priv, _ := ed25519.GenerateKey(rand.Reader)
	for audience := 0; audience < 10; audience++ {
		t.Run(fmt.Sprintf("audience-%d", audience), func(t *testing.T) {
			a := Authorization{Version: 1, ID: fmt.Sprint(audience), Subject: fmt.Sprint(audience), PolicyEpoch: "1", SourceView: head, Active: true, ValidUntil: testNow.Add(time.Hour).Format(time.RFC3339)}
			for i, r := range records {
				if i%10 == audience {
					a.Records = append(a.Records, AuthorizeRecord(r))
				}
			}
			signed := signedGrant(t, a, priv)
			dst := Store{filepath.Join(t.TempDir(), "image")}
			id, e := src.CompileAuthorized(dst, signed, pub, a.Subject, a.PolicyEpoch, testNow)
			if e != nil {
				t.Fatal(e)
			}
			v := open(t, dst, id)
			if e = v.CheckAuthorization(signed, pub, a.Subject, a.PolicyEpoch, testNow); e != nil {
				t.Fatal(e)
			}
			for i, r := range records {
				_, e := v.Get(r.Ref, nil, testNow)
				if (e == nil) != (i%10 == audience) {
					t.Fatalf("wrong exposure for object %d", i)
				}
			}
			second := Store{filepath.Join(t.TempDir(), "same-authorization")}
			again, e := src.CompileAuthorized(second, signed, pub, a.Subject, a.PolicyEpoch, testNow)
			if e != nil || again != id {
				t.Fatal("same authorization is not reusable")
			}
		})
	}
}

func TestAuthorizedCompilerRejectsInactiveAndTemporalSources(t *testing.T) {
	for _, name := range []string{"retired", "pending", "suppressed", "expired", "not yet valid"} {
		t.Run(name, func(t *testing.T) {
			src := Store{t.TempDir()}
			r := record("general", "1", "restricted object")
			switch name {
			case "retired", "pending":
				r.Lifecycle = name
			case "suppressed":
				r.Suppressed = true
			case "expired":
				r.ValidUntil = testNow.Format(time.RFC3339)
			case "not yet valid":
				r.ValidFrom = testNow.Add(time.Hour).Format(time.RFC3339)
			}
			head := build(t, src, changes("general", "general", "", r))
			pub, priv, _ := ed25519.GenerateKey(rand.Reader)
			a := Authorization{Version: 1, ID: "grant", Subject: "subject", PolicyEpoch: "1", SourceView: head, Active: true, ValidUntil: testNow.Add(time.Hour).Format(time.RFC3339), Records: []AuthorizedRecord{AuthorizeRecord(r)}}
			dst := Store{filepath.Join(t.TempDir(), "model")}
			if _, e := src.CompileAuthorized(dst, signedGrant(t, a, priv), pub, a.Subject, a.PolicyEpoch, testNow); e == nil {
				t.Fatal("ineligible source escaped")
			}
		})
	}
}
func TestAuthorizedImageRejectsUnreachableForeignObjects(t *testing.T) {
	src, _, _, a, pub, priv := authorizationFixture(t)
	signed := signedGrant(t, a, priv)
	dst := Store{filepath.Join(t.TempDir(), "model")}
	id, e := src.CompileAuthorized(dst, signed, pub, a.Subject, a.PolicyEpoch, testNow)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = dst.put([]byte("CANARY_FOREIGN_UNREACHABLE")); e != nil {
		t.Fatal(e)
	}
	if e = open(t, dst, id).CheckAuthorization(signed, pub, a.Subject, a.PolicyEpoch, testNow); e == nil {
		t.Fatal("foreign physical object accepted")
	}
}

func TestResolveResponseNamespacedIdentity(t *testing.T) {
	s, head, rs, a, _, _ := authorizationFixture(t)
	v := open(t, s, head)
	// Both approved layers use ID 1. The release must retain both namespaces.
	raw, _ := json.Marshal(map[string]any{"facts": []any{
		map[string]any{"id": 1, "content": rs[0].Content},
		map[string]any{"id": "1", "content": rs[1].Content},
	}})
	refs, err := v.ResolveResponse(raw, a, testNow)
	if err != nil || len(refs) != 2 || refs[0] != rs[0].Ref || refs[1] != rs[1].Ref {
		t.Fatalf("lost identity: %v %v", refs, err)
	}
	// A model cannot claim a namespace or supply its own canonical mapping.
	forged, _ := json.Marshal(map[string]any{"facts": []any{map[string]any{"id": 1, "content": rs[0].Content, "memory_ref": rs[1].Ref}}})
	if _, err = v.ResolveResponse(forged, a, testNow); err == nil {
		t.Fatal("accepted forged reference")
	}
}
func TestResolveResponseAmbiguousLegacyIdentity(t *testing.T) {
	s := Store{t.TempDir()}
	g := record("general", "1", "same content")
	k := record("kb", "1", "same content")
	base := build(t, s, changes("general", "general", "", g))
	head := build(t, s, changes("kb", "kb", base, k))
	v := open(t, s, head)
	a := Authorization{Records: []AuthorizedRecord{AuthorizeRecord(g), AuthorizeRecord(k)}}
	raw := json.RawMessage(`{"facts":[{"id":1,"content":"same content"}]}`)
	if _, err := v.ResolveResponse(raw, a, testNow); err == nil {
		t.Fatal("ambiguous ID was silently selected")
	}
}
