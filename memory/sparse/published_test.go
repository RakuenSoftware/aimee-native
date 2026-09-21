package sparse

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestPublishedReaderWithoutGrantFiles(t *testing.T) {
	src, _, rs, a, pub, priv := authorizationFixture(t)
	a.ReferenceLookups = []ReferenceLookupPolicy{{"general", "test", "exact-key-v1"}}
	dst := Store{filepath.Join(t.TempDir(), "recipient")}
	id, err := src.CompileAuthorized(dst, signedGrant(t, a, priv), pub, a.Subject, a.PolicyEpoch, testNow)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(dst.Root, "AUTHORIZATION.json")); !os.IsNotExist(err) {
		t.Fatal("grant distributed to local reader")
	}
	p, err := dst.OpenPublished(id)
	if err != nil {
		t.Fatal(err)
	}
	defer p.Close()
	// Grant lifetime does not gate reads of bytes already delivered. Record
	// temporal semantics still apply independently. The publisher withdraws data.
	r, err := p.Recall(rs[0].Key, 4, "test", testNow.Add(2*time.Hour))
	if err != nil || r.Outcome != "hit" {
		t.Fatalf("%+v %v", r, err)
	}
	var body struct {
		Facts []struct {
			MemoryRef Ref `json:"memory_ref"`
		}
	}
	if json.Unmarshal(r.Response, &body) != nil || len(body.Facts) != 1 || body.Facts[0].MemoryRef != rs[0].Ref {
		t.Fatal(string(r.Response))
	}
	if got, err := p.Recall("CANARY_UNAPPROVED_GLOBAL", 4, "test", testNow); err != nil || got.Outcome != "uncovered" {
		t.Fatalf("%+v %v", got, err)
	}
	// The actual protection: excluded bytes are absent, even when the entire
	// recipient directory is read directly instead of using its lookup API.
	if err := filepath.WalkDir(dst.Root, func(path string, d os.DirEntry, e error) error {
		if e != nil {
			return e
		}
		if d.IsDir() {
			return nil
		}
		b, e := os.ReadFile(path)
		if bytes.Contains(b, []byte("CANARY_")) {
			t.Errorf("excluded bytes at %s", path)
		}
		return e
	}); err != nil {
		t.Fatal(err)
	}
	// Even the public/general records must be approved BEFORE distribution.
	a.Active = false
	if _, err := src.CompileAuthorized(Store{filepath.Join(t.TempDir(), "denied")}, signedGrant(t, a, priv), pub, a.Subject, a.PolicyEpoch, testNow); err == nil {
		t.Fatal("publisher accepted denied source")
	}
}

func TestPublishedReaderRefusesRawSource(t *testing.T) {
	s, head, _, _, _, _ := authorizationFixture(t)
	if p, err := s.OpenPublished(head); err == nil {
		p.Close()
		t.Fatal("raw source accepted as a recipient snapshot")
	}
}
