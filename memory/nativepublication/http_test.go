package nativepublication

import (
	"bytes"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func fixture(t *testing.T) (*Handler, *bool, *string) {
	t.Helper()
	dir := t.TempDir()
	for _, name := range []string{"index.json", "compact.pack"} {
		if e := os.WriteFile(filepath.Join(dir, name), []byte(name), 0600); e != nil {
			t.Fatal(e)
		}
	}
	enabled := true
	scope := "alice-policy-1"
	h := &Handler{Resolve: func(r *http.Request) (Access, error) {
		if !enabled || r.Header.Get("Authorization") != "Bearer test-only" {
			return Access{}, errors.New("denied")
		}
		return Access{Scope: scope, Recipient: "alice", Prepare: func(*http.Request, string) (Prepared, error) {
			return Prepared{Root: dir, Recipient: "alice", Model: "gemma", Key: strings.Repeat("a", 64), View: strings.Repeat("b", 64), Records: []Record{{"n", "1", "r"}, {"n", "2", "r"}, {"n", "3", "r"}}}, nil
		}, Check: func(*http.Request, Prepared) error {
			if !enabled {
				return errors.New("withdrawn")
			}
			return nil
		}}, nil
	}}
	return h, &enabled, &scope
}
func request(h *Handler, method, path, body string, authenticated bool) *httptest.ResponseRecorder {
	r := httptest.NewRequest(method, path, bytes.NewBufferString(body))
	if authenticated {
		r.Header.Set("Authorization", "Bearer test-only")
	}
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	return w
}
func selectOffer(t *testing.T, h *Handler) Offer {
	t.Helper()
	w := request(h, "POST", "/v1/native/select", `{"query":"all three facts"}`, true)
	if w.Code != 200 {
		t.Fatalf("select status %d: %s", w.Code, w.Body)
	}
	var o Offer
	if e := json.Unmarshal(w.Body.Bytes(), &o); e != nil {
		t.Fatal(e)
	}
	return o
}
func TestDeliveryRequiresCurrentAuthorityAndPreservesAllRecords(t *testing.T) {
	h, enabled, scope := fixture(t)
	if w := request(h, "POST", "/v1/native/select", `{"query":"x"}`, false); w.Code != 403 {
		t.Fatal(w.Code)
	}
	o := selectOffer(t, h)
	if len(o.Records) != 3 || len(o.Artifacts) != 2 {
		t.Fatal(o)
	}
	raw, _ := json.Marshal(o)
	if strings.Contains(string(raw), "root") || strings.Contains(string(raw), "Root") {
		t.Fatal("private path leaked")
	}
	base := "/v1/native/leases/" + o.Lease + "/"
	for _, a := range o.Artifacts {
		w := request(h, "GET", base+a.Name, "", true)
		if w.Code != 200 || int64(w.Body.Len()) != a.Bytes {
			t.Fatal(w.Code, w.Body)
		}
	}
	if w := request(h, "POST", base+"approve", "", true); w.Code != 200 {
		t.Fatal(w.Code)
	}
	*scope = "alice-policy-2"
	if w := request(h, "GET", base+"compact.pack", "", true); w.Code != 403 {
		t.Fatal("old policy delivered", w.Code)
	}
	*scope = "alice-policy-1"
	*enabled = false
	if w := request(h, "POST", base+"approve", "", true); w.Code != 403 {
		t.Fatal("withdrawn publication approved", w.Code)
	}
}
func TestExpiryBoundedLeasesAndNoCallerAuthority(t *testing.T) {
	h, _, _ := fixture(t)
	h.MaxLeases = 1
	o := selectOffer(t, h)
	if w := request(h, "POST", "/v1/native/select", `{"query":"x"}`, true); w.Code != 429 {
		t.Fatal(w.Code)
	}
	h.mu.Lock()
	l := h.leases[o.Lease]
	l.offer.Expires = time.Now().Add(-time.Second).Unix()
	h.leases[o.Lease] = l
	h.mu.Unlock()
	if w := request(h, "POST", "/v1/native/leases/"+o.Lease+"/approve", "", true); w.Code != 403 {
		t.Fatal(w.Code)
	}
	selectOffer(t, h)
	for _, body := range []string{`{"query":"x","recipient":"bob"}`, `{"query":"x","publication":"other"}`, `{"query":"x"} {}`, `{"query":""}`} {
		if w := request(h, "POST", "/v1/native/select", body, true); w.Code != 400 {
			t.Fatal(body, w.Code)
		}
	}
}
func TestWithdrawalDuringPreparationAndWrongRecipient(t *testing.T) {
	h, enabled, _ := fixture(t)
	original := h.Resolve
	h.Resolve = func(r *http.Request) (Access, error) {
		a, e := original(r)
		if e != nil {
			return a, e
		}
		p := a.Prepare
		a.Prepare = func(r *http.Request, q string) (Prepared, error) { v, e := p(r, q); *enabled = false; return v, e }
		return a, nil
	}
	if w := request(h, "POST", "/v1/native/select", `{"query":"x"}`, true); w.Code != 403 {
		t.Fatal(w.Code)
	}
	h, _, _ = fixture(t)
	original = h.Resolve
	h.Resolve = func(r *http.Request) (Access, error) {
		a, e := original(r)
		p := a.Prepare
		a.Prepare = func(r *http.Request, q string) (Prepared, error) { v, e := p(r, q); v.Recipient = "bob"; return v, e }
		return a, e
	}
	if w := request(h, "POST", "/v1/native/select", `{"query":"x"}`, true); w.Code != 503 {
		t.Fatal(w.Code)
	}
}
