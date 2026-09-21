package sparse

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestAuthenticatedPublicationTransport(t *testing.T) {
	one, id1 := deliveryFixture(t, true)
	two, id2 := deliveryFixture(t, false)
	selected := one
	allowed := true
	calls := 0
	handler := PublicationHandler(func(r *http.Request) (Store, error) {
		calls++
		if !allowed || r.Header.Get("Authorization") != "Bearer authorized-recipient" {
			return Store{}, errors.New("denied")
		}
		return selected, nil
	})
	server := httptest.NewTLSServer(handler)
	defer server.Close()
	d := Delivery{filepath.Join(t.TempDir(), "recipient")}
	request, _ := http.NewRequest("GET", server.URL, nil)
	request.Header.Set("Authorization", "Bearer authorized-recipient")
	fetch := func() PublicationResult {
		t.Helper()
		r, e := FetchPublication(context.Background(), server.Client(), request, d, -1, 1<<20)
		if e != nil {
			t.Fatal(e)
		}
		return r
	}
	if r := fetch(); r.State != "installed" || r.View != id1 {
		t.Fatalf("%+v", r)
	}
	if r := fetch(); r.State != "unchanged" {
		t.Fatalf("%+v", r)
	}
	if calls != 2 {
		t.Fatal("conditional download bypassed authorization")
	}
	selected = two
	if r := fetch(); r.State != "installed" || r.View != id2 {
		t.Fatalf("%+v", r)
	}
	if _, e := os.Stat(filepath.Join(d.Root, "snapshots", id1)); !os.IsNotExist(e) {
		t.Fatal("old payload retained")
	}
	allowed = false
	if r := fetch(); r.State != "withdrawn" {
		t.Fatalf("%+v", r)
	}
	if _, e := (Store{d.Root}).PinPublished(nil); e == nil {
		t.Fatal("revoked delivery readable")
	}
	allowed = true
	if r := fetch(); r.State != "installed" {
		t.Fatalf("%+v", r)
	}
	os.Remove(filepath.Join(two.Root, "CURRENT"))
	if r := fetch(); r.State != "withdrawn" {
		t.Fatalf("%+v", r)
	}
}
func TestPublicationRejectsRawAndFailedTransfers(t *testing.T) {
	raw, _, _, _, _, _ := authorizationFixture(t)
	valid, _ := deliveryFixture(t, false)
	for _, mode := range []string{"raw", "partial", "redirect", "oversize", "unavailable"} {
		t.Run(mode, func(t *testing.T) {
			d := Delivery{filepath.Join(t.TempDir(), "recipient")}
			if _, e := d.Install(valid, "", -1); e != nil {
				t.Fatal(e)
			}
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				switch mode {
				case "raw":
					PublicationHandler(func(*http.Request) (Store, error) { return raw, nil }).ServeHTTP(w, r)
				case "partial":
					w.Header().Set("ETag", `"`+digest([]byte("head"))+`"`)
					w.Write([]byte("truncated archive"))
				case "redirect":
					http.Redirect(w, r, "https://wrong-recipient.invalid", 302)
				case "oversize":
					w.Header().Set("Content-Length", "9999999999")
					w.WriteHeader(200)
				default:
					w.WriteHeader(503)
				}
			}))
			defer server.Close()
			request, _ := http.NewRequest("GET", server.URL, nil)
			r, e := FetchPublication(context.Background(), server.Client(), request, d, -1, 1<<20)
			if e != nil || r.State != "withdrawn" {
				t.Fatalf("%+v %v", r, e)
			}
			if _, e := (Store{d.Root}).PinPublished(nil); e == nil {
				t.Fatal("stale delivery remains")
			}
		})
	}
}
