// Synthetic fixture built through the real scoped-image compiler. No production authority.
package main

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"flag"
	"fmt"
	"github.com/RakuenSoftware/aimee-native/memory/sparse"
	"os"
	"path/filepath"
	"time"
)

func main() {
	root := flag.String("root", "", "new fixture directory")
	factsPath := flag.String("facts", "", "optional JSON fixture content/cue pairs (1-32)")
	flag.Parse()
	if *root == "" {
		panic("root required")
	}
	if _, e := os.Stat(*root); !os.IsNotExist(e) {
		panic("use a new fixture directory")
	}
	contents := []string{"The user's private vault code is 68731.", "The user's private project codename is Kestrel.", "The user's preferred meeting drink is rooibos.", "The user's private vault code is 94268.", "The user's private project codename is Osprey.", "The user's preferred meeting drink is ginger tea."}
	var supplied []struct {
		Content string `json:"content"`
		Cue     string `json:"cue"`
	}
	if *factsPath != "" {
		raw, e := os.ReadFile(*factsPath)
		if e != nil {
			panic(e)
		}
		if e = json.Unmarshal(raw, &supplied); e != nil {
			panic(e)
		}
		if len(supplied) < 1 || len(supplied) > 32 {
			panic("fixture requires 1-32 facts")
		}
		contents = nil
		for _, f := range supplied {
			if f.Content == "" || f.Cue == "" {
				panic("empty fixture")
			}
			contents = append(contents, f.Content)
		}
	}
	var records []sparse.Record
	var approved []sparse.AuthorizedRecord
	var cues []sparse.ReferenceCue
	for i, text := range contents {
		r := sparse.Record{Ref: sparse.Ref{Namespace: "fixture", ID: fmt.Sprint(i + 1), Revision: "1"}, Scope: sparse.Scope{Type: "global", Value: "_global"}, Key: fmt.Sprintf("fixture-%d", i+1), Content: text, Kind: "fact", Tier: "working", Confidence: 1, Lifecycle: "active"}
		records = append(records, r)
		approved = append(approved, sparse.AuthorizeRecord(r))
		cue := "alpha"
		if i >= 3 {
			cue = "beta"
		}
		cue += " " + []string{"vault", "project", "drink"}[i%3]
		if len(supplied) > 0 {
			cue = supplied[i].Cue
		}
		cues = append(cues, sparse.ReferenceCue{Ref: r.Ref, Cue: cue, Authority: "lab"})
	}
	source := sparse.Store{Root: filepath.Join(*root, "source")}
	head, e := source.Build(sparse.ChangeSet{Namespace: "fixture", Kind: "general", Generation: 1, Records: records, Source: "synthetic selection fixture", Coverage: []string{"memory_records"}})
	if e != nil {
		panic(e)
	}
	pub, key, e := ed25519.GenerateKey(rand.Reader)
	if e != nil {
		panic(e)
	}
	now := time.Now()
	authorization := sparse.Authorization{Version: 1, ID: "synthetic-selection", Subject: "synthetic-validation", PolicyEpoch: "fixture", SourceView: head, Active: true, ValidUntil: now.Add(time.Hour).UTC().Format(time.RFC3339Nano), Grants: []string{"global:_global"}, Records: approved, ReferenceCues: cues}
	signed, e := sparse.SignAuthorization(authorization, key)
	if e != nil {
		panic(e)
	}
	recipient := sparse.Store{Root: filepath.Join(*root, "recipient")}
	id, e := source.CompileAuthorized(recipient, signed, pub, authorization.Subject, authorization.PolicyEpoch, now)
	if e != nil {
		panic(e)
	}
	json.NewEncoder(os.Stdout).Encode(map[string]any{"view": id, "root": recipient.Root, "records": records, "authority": "ephemeral synthetic fixture; not production authorization"})
}
