package main

import (
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"github.com/RakuenSoftware/aimee-qwen/memory/sparse"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestGeneralKBAndPrivateOverlay(t *testing.T) {
	for _, viaKB := range []bool{false, true} {
		t.Run(map[bool]string{false: "direct", true: "via_kb"}[viaKB], func(t *testing.T) {
			store := sparse.Store{Root: t.TempDir()}
			base, err := build(store.Root, "../../knowledge/general-v0/records.json")
			if err != nil {
				t.Fatal(err)
			}
			raw, _ := os.ReadFile("../../knowledge/general-v0/records.json")
			var seed sparse.ChangeSet
			_ = json.Unmarshal(raw, &seed)
			now := time.Now()
			until := now.Add(time.Hour).Format(time.RFC3339)
			mk := func(ns, content string, scope sparse.Scope) sparse.Record {
				return sparse.Record{Ref: sparse.Ref{Namespace: ns, ID: "1", Revision: "v1"}, Scope: scope, Key: "fixture.setting", Content: content, Kind: "fact", Tier: "L3", Confidence: 1, Lifecycle: "active"}
			}
			upstream := base
			var kb, kbAllowed sparse.Record
			grants := []string{"user:_user"}
			grantMap := map[string]bool{"user:_user": true}
			if viaKB {
				kb = mk("fixture-kb", "CANARY_OTHER_PROJECT", sparse.Scope{Type: "project", Value: "other"})
				kbAllowed = mk("fixture-kb", "KB calibration uses zircon", sparse.Scope{Type: "project", Value: "alpha"})
				kbAllowed.ID = "7"
				grants = append(grants, "project:alpha")
				grantMap["project:alpha"] = true
				upstream, err = store.Build(sparse.ChangeSet{Namespace: "fixture-kb", Kind: "kb", Generation: 1, Upstream: base, Records: []sparse.Record{kb, kbAllowed}, Source: "synthetic KB", Coverage: []string{"facts"}})
				if err != nil {
					t.Fatal(err)
				}
			}
			local := mk("fixture-server", "local preference is oolong", sparse.Scope{Type: "user", Value: "_user"})
			forbidden := local
			forbidden.ID = "2"
			forbidden.Content = "CANARY_WITHHELD_USER"
			forbidden.Metadata = json.RawMessage(`{"secret":"CANARY_METADATA"}`)
			public := seedRecord(t, "si.prefix.kilo")
			response, _ := json.Marshal(map[string]any{"status": "ok", "facts": []any{map[string]any{"id": public.ID, "content": public.Content}, map[string]any{"id": local.ID, "content": local.Content}}, "windows": []any{}, "active_context_missing": false})
			contract := sparse.ReadContract{Query: "kilo and my preference", Limit: 2, Authority: "fixture", Grants: grants, ValidUntil: until, Dependencies: []sparse.Ref{public.Ref, local.Ref}, Response: response}
			c := sparse.ChangeSet{Namespace: "fixture-server", Kind: "server", Generation: 1, Upstream: upstream, Records: []sparse.Record{local, forbidden}, ReadContracts: []sparse.ReadContract{contract}, Source: "synthetic server", Coverage: []string{"facts"}}
			head, err := store.Build(c)
			if err != nil {
				t.Fatal(err)
			}
			pub, priv, _ := ed25519.GenerateKey(rand.Reader)
			auth := sparse.Authorization{Version: 1, ID: "fixture", Subject: "fixture-model", PolicyEpoch: "1", SourceView: head, Active: true, ValidUntil: until, Grants: grants, Records: []sparse.AuthorizedRecord{sparse.AuthorizeRecord(public), sparse.AuthorizeRecord(local)}, ReadDigests: []string{sparse.ReadDigest(contract)}}
			if viaKB {
				auth.Records = append(auth.Records, sparse.AuthorizeRecord(kbAllowed))
			}
			signed, _ := sparse.SignAuthorization(auth, priv)
			target := sparse.Store{Root: filepath.Join(t.TempDir(), "model")}
			id, err := store.CompileAuthorized(target, signed, pub, auth.Subject, auth.PolicyEpoch, now)
			if err != nil {
				t.Fatal(err)
			}
			view, err := target.Open(id)
			if err != nil {
				t.Fatal(err)
			}
			defer view.Close()
			if err = view.CheckAuthorization(signed, pub, auth.Subject, auth.PolicyEpoch, now); err != nil {
				t.Fatal(err)
			}
			if viaKB {
				if _, err := view.Get(kbAllowed.Ref, grantMap, now); err != nil {
					t.Fatal(err)
				}
				if len(view.Layers) != 3 {
					t.Fatal("missing KB layer")
				}
			}
			result := view.Recall(contract.Query, 2, "fixture", grantMap, now)
			if result.Outcome != "hit" {
				t.Fatal(result)
			}
			refs, err := view.ResolveResponse(result.Response, auth, now)
			if err != nil || len(refs) != 2 || refs[0] != public.Ref || refs[1] != local.Ref {
				t.Fatalf("bad mixed refs: %v %v", refs, err)
			}
			if view.Recall("complex unapproved query", 2, "fixture", grantMap, now).Outcome != "uncovered" {
				t.Fatal("invented local answer")
			}
			_ = filepath.Walk(target.Root, func(path string, info os.FileInfo, e error) error {
				if e == nil && !info.IsDir() {
					raw, _ := os.ReadFile(path)
					if bytes.Contains(raw, []byte("CANARY_")) {
						t.Fatalf("private bytes in model image %s", path)
					}
				}
				return e
			})
			// Aimee explicitly withdraws the public record for this user's view.
			c.Generation = 2
			c.Previous = head
			c.Records = nil
			c.ReadContracts = nil
			c.Suppressions = []sparse.Suppression{{Target: public.Ref, Scope: local.Scope, Reason: "fixture authoritative contradiction decision"}}
			updated, err := store.Build(c)
			if err != nil {
				t.Fatal(err)
			}
			auth.SourceView = updated
			signed, _ = sparse.SignAuthorization(auth, priv)
			if _, err = store.CompileAuthorized(sparse.Store{Root: filepath.Join(t.TempDir(), "stale")}, signed, pub, auth.Subject, auth.PolicyEpoch, now); err == nil {
				t.Fatal("suppressed general record exported")
			}
			auth.Records = []sparse.AuthorizedRecord{sparse.AuthorizeRecord(local)}
			auth.ReadDigests = nil
			signed, _ = sparse.SignAuthorization(auth, priv)
			if _, err = store.CompileAuthorized(sparse.Store{Root: filepath.Join(t.TempDir(), "updated")}, signed, pub, auth.Subject, auth.PolicyEpoch, now); err != nil {
				t.Fatal(err)
			}
		})
	}
}
func seedRecord(t *testing.T, id string) sparse.Record {
	t.Helper()
	raw, err := os.ReadFile("../../knowledge/general-v0/records.json")
	if err != nil {
		t.Fatal(err)
	}
	var c sparse.ChangeSet
	_ = json.Unmarshal(raw, &c)
	for _, r := range c.Records {
		if r.ID == id {
			return r
		}
	}
	t.Fatal("missing seed record")
	return sparse.Record{}
}
