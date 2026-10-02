package nativepublication

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestPrivateCompilerRootIsDecodedButNeverDelivered(t *testing.T) {
	dir := t.TempDir()
	binary := filepath.Join(dir, "compiler")
	template := filepath.Join(dir, "config.json")
	output := `{"root":"/private/native/artifact","recipient":"alice","model":"gemma","key":"key","authorized_view":"view","records":[{"namespace":"n","id":"1","revision":"r"}],"reused":true}`
	if e := os.WriteFile(binary, []byte("#!/bin/sh\nprintf '%s\\n' '"+output+"'\n"), 0700); e != nil {
		t.Fatal(e)
	}
	if e := os.WriteFile(template, []byte(`{"recipient":"alice","model_revision":"gemma"}`), 0600); e != nil {
		t.Fatal(e)
	}
	p := Preparer{Binary: binary, Template: template, Profile: Profile{Schema: 1, Recipient: "alice", Model: "gemma"}}
	result, e := p.execute(context.Background(), "alice", "private query", false)
	if e != nil {
		t.Fatal(e)
	}
	if result.Root != "/private/native/artifact" || result.Query != "private query" {
		t.Fatal("private control fields were lost")
	}
	raw, e := json.Marshal(result)
	if e != nil {
		t.Fatal(e)
	}
	if strings.Contains(string(raw), "/private/") || strings.Contains(string(raw), "private query") {
		t.Fatal("private control fields leaked into delivery")
	}
	if _, e = p.execute(context.Background(), "bob", "private query", false); e == nil {
		t.Fatal("wrong recipient accepted")
	}
	p.Profile.Model = "another-model"
	if _, e = p.execute(context.Background(), "alice", "private query", false); e == nil {
		t.Fatal("wrong model accepted")
	}
}
