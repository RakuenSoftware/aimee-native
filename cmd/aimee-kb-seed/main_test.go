package main

import (
	"encoding/json"
	"github.com/JBailes/aimee/server-go/modules/memory/sparse"
	"os"
	"path/filepath"
	"testing"
)

func TestSeedBuildReproducible(t *testing.T) {
	path := "../../knowledge/general-v0/records.json"
	a, err := build(t.TempDir(), path)
	if err != nil {
		t.Fatal(err)
	}
	b, err := build(t.TempDir(), path)
	if err != nil || a != b {
		t.Fatalf("nonrepeatable build: %s %s %v", a, b, err)
	}
	raw, _ := os.ReadFile(path)
	var c sparse.ChangeSet
	if json.Unmarshal(raw, &c) != nil || len(c.Records) != 25 {
		t.Fatal("unexpected starter corpus")
	}
	for _, r := range c.Records {
		if r.Scope != (sparse.Scope{Type: "global", Value: "_global"}) {
			t.Fatal("nonpublic seed")
		}
	}
}
func TestRejectPrivateSeedAndMissingProvenance(t *testing.T) {
	raw, _ := os.ReadFile("../../knowledge/general-v0/records.json")
	for _, kind := range []string{"private", "no-provenance"} {
		t.Run(kind, func(t *testing.T) {
			var c sparse.ChangeSet
			_ = json.Unmarshal(raw, &c)
			if kind == "private" {
				c.Records[0].Scope = sparse.Scope{Type: "user", Value: "_user"}
			} else {
				c.Records[0].Metadata = nil
			}
			raw, _ := json.Marshal(c)
			p := filepath.Join(t.TempDir(), "input.json")
			_ = os.WriteFile(p, raw, 0600)
			if _, err := build(t.TempDir(), p); err == nil {
				t.Fatal("invalid source accepted")
			}
		})
	}
}
