package main

import (
	"bytes"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/RakuenSoftware/aimee-qwen/memory/sparse"
)

func TestBuildPublishImportAndPersistentReader(t *testing.T) {
	root := t.TempDir()
	input := filepath.Join(t.TempDir(), "source.json")
	c := sparse.ChangeSet{Namespace: "general", Kind: "general", Generation: 1, Source: "test", Coverage: []string{"facts"}, Records: []sparse.Record{{Ref: sparse.Ref{Namespace: "general", ID: "1", Revision: "v1"}, Scope: sparse.Scope{Type: "global", Value: "_global"}, Key: "beacon", Content: "beacon teal", Confidence: 1, Lifecycle: "active"}}}
	b, _ := json.Marshal(c)
	if err := os.WriteFile(input, b, 0600); err != nil {
		t.Fatal(err)
	}
	var out bytes.Buffer
	if err := run([]string{"build", "--root", root, "--input", input}, nil, &out); err != nil {
		t.Fatal(err)
	}
	var result map[string]string
	if err := json.Unmarshal(out.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	id := result["view"]
	if err := run([]string{"publish", "--root", root, "--view", id}, nil, &out); err != nil {
		t.Fatal(err)
	}
	out.Reset()
	if err := run([]string{"serve", "--unsafe-research", "--root", root}, strings.NewReader("{\"op\":\"pin\"}\n{\"op\":\"search\",\"query\":\"beacon\",\"limit\":4}\n"), &out); err != nil {
		t.Fatal(err)
	}
	lines := strings.Split(strings.TrimSpace(out.String()), "\n")
	if len(lines) != 2 || !strings.Contains(lines[1], "beacon teal") {
		t.Fatalf("serve: %s", out.String())
	}
	out.Reset()
	if err := run([]string{"export", "--internal-backup", "--root", root}, nil, &out); err != nil {
		t.Fatal(err)
	}
	archive := filepath.Join(t.TempDir(), "image.tar")
	if err := os.WriteFile(archive, out.Bytes(), 0600); err != nil {
		t.Fatal(err)
	}
	other := t.TempDir()
	out.Reset()
	if err := run([]string{"import", "--internal-backup", "--root", other, "--input", archive}, nil, &out); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.String(), id) {
		t.Fatal("import changed identity")
	}
	if _, err := os.Stat(filepath.Join(other, "CURRENT")); !os.IsNotExist(err) {
		t.Fatal("import implicitly published")
	}
	out.Reset()
	if err := run([]string{"query", "--root", other, "--view", id, "--query", "beacon"}, nil, &out); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.String(), "beacon teal") {
		t.Fatal("imported query failed")
	}
}

func TestUnboundModelServingAndRawTransferFailClosed(t *testing.T) {
	for _, command := range []string{"import", "export-postgres"} {
		var out bytes.Buffer
		if err := run([]string{command, "--root", t.TempDir()}, nil, &out); err == nil || out.Len() != 0 {
			t.Fatalf("unapproved %s accepted", command)
		}
	}
	root := t.TempDir()
	store := sparse.Store{Root: root}
	view, err := store.Build(sparse.ChangeSet{Namespace: "general", Kind: "general", Generation: 1, Source: "test", Coverage: []string{"facts"}})
	if err != nil {
		t.Fatal(err)
	}
	if err = store.Publish(view, ""); err != nil {
		t.Fatal(err)
	}
	for _, command := range []string{"serve", "export"} {
		var out bytes.Buffer
		if err = run([]string{command, "--root", root}, strings.NewReader("{\"op\":\"pin\"}\n"), &out); err == nil || out.Len() != 0 {
			t.Fatalf("unapproved %s accepted", command)
		}
	}
}

func TestPublishedReaderDropsPinnedStateAfterWithdrawalCheck(t *testing.T) {
	s := sparse.Store{Root: t.TempDir()}
	id, e := s.Build(sparse.ChangeSet{Namespace: "general", Kind: "general", Generation: 1, Source: "authorized knowledge snapshot", Coverage: []string{"test"}, Authorization: "released", Serving: &sparse.ServingConfig{Version: 1, ReferenceLookups: []sparse.ReferenceLookupPolicy{{Namespace: "general", Authority: "test", Mode: "exact-key-v1"}}}, Records: []sparse.Record{{Ref: sparse.Ref{Namespace: "general", ID: "1", Revision: "1"}, Scope: sparse.Scope{Type: "global", Value: "_global"}, Key: "test planet", Content: "Mercury", Kind: "fact", Lifecycle: "active", Confidence: 1}}})
	if e != nil {
		t.Fatal(e)
	}
	if e = s.Publish(id, ""); e != nil {
		t.Fatal(e)
	}
	requests, send := io.Pipe()
	responses, reply := io.Pipe()
	done := make(chan error, 1)
	go func() { done <- servePublished(s, requests, reply); reply.Close() }()
	encoder := json.NewEncoder(send)
	decoder := json.NewDecoder(responses)
	ask := func(op string) map[string]any {
		t.Helper()
		if e := encoder.Encode(map[string]any{"op": op, "query": "test planet", "authority": "test", "limit": 4}); e != nil {
			t.Fatal(e)
		}
		var r map[string]any
		if e := decoder.Decode(&r); e != nil {
			t.Fatal(e)
		}
		return r
	}
	if ask("pin")["view"] != id {
		t.Fatal("pin failed")
	}
	if ask("recall")["outcome"] != "hit" {
		t.Fatal("recall failed")
	}
	if e = os.Remove(filepath.Join(s.Root, "CURRENT")); e != nil {
		t.Fatal(e)
	}
	if ask("check")["error"] == nil {
		t.Fatal("withdrawal not reported")
	}
	if ask("recall")["error"] != "snapshot is not pinned" {
		t.Fatal("withdrawn pinned state remained usable")
	}
	send.Close()
	if e = <-done; e != nil {
		t.Fatal(e)
	}
	requests.Close()
	responses.Close()
}

func TestNativePublishedProtocolBindingAndWithdrawal(t *testing.T) {
	s := sparse.Store{Root: t.TempDir()}
	ref := sparse.Ref{Namespace: "general", ID: "one", Revision: "1"}
	id, e := s.Build(sparse.ChangeSet{Namespace: "general", Kind: "general", Generation: 1, Source: "authorized knowledge snapshot", Coverage: []string{"test"}, Authorization: "released", Serving: &sparse.ServingConfig{Version: 1, CandidateRoutes: []sparse.CandidateRoute{{Partition: "one", Authority: "test", Cues: []string{"beacon"}, Records: []sparse.Ref{ref}}}}, Records: []sparse.Record{{Ref: ref, Scope: sparse.Scope{Type: "global", Value: "_global"}, Key: "beacon record", Content: "teal", Kind: "fact", Lifecycle: "active", Confidence: 1}}})
	if e != nil {
		t.Fatal(e)
	}
	if e = s.Publish(id, ""); e != nil {
		t.Fatal(e)
	}
	input, send := io.Pipe()
	output, reply := io.Pipe()
	done := make(chan error, 1)
	go func() { done <- servePublished(s, input, reply); reply.Close() }()
	encoder := json.NewEncoder(send)
	decoder := json.NewDecoder(output)
	ask := func(req any) map[string]any {
		t.Helper()
		if e := encoder.Encode(req); e != nil {
			t.Fatal(e)
		}
		var r map[string]any
		if e := decoder.Decode(&r); e != nil {
			t.Fatal(e)
		}
		return r
	}
	if ask(map[string]any{"op": "pin"})["view"] != id {
		t.Fatal("pin failed")
	}
	address := sparse.NativeAddress{Schema: 1, View: id, Representation: "text-query-v1"}
	req := map[string]any{"op": "native_recall", "query": "beacon", "limit": 2, "authority": "test", "address": address}
	if r := ask(req); r["outcome"] != "hit" || r["candidate_records"] != float64(1) {
		t.Fatal(r)
	}
	address.View = "wrong"
	req["address"] = address
	if r := ask(req); r["error"] == nil {
		t.Fatal("unbound address accepted")
	}
	address.View = id
	req["address"] = address
	if e = os.Remove(filepath.Join(s.Root, "CURRENT")); e != nil {
		t.Fatal(e)
	}
	if r := ask(req); r["error"] == nil || r["response"] != nil {
		t.Fatal("withdrawn record returned", r)
	}
	send.Close()
	if e = <-done; e != nil {
		t.Fatal(e)
	}
	input.Close()
	output.Close()
}
