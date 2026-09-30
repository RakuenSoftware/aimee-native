// Package nativepublication delivers prepared native memory behind Aimee's
// authenticated API. It owns transport, not identity, selection or release policy.
package nativepublication

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// Access must be resolved afresh using Aimee's authenticated identity and current
// release policy. Scope must include the recipient and policy revision. No value
// in the request body is authority. Check must revalidate the prepared view and
// every selected record, including after a long compilation or download.
type Profile struct {
	Schema            int    `json:"schema"`
	Recipient         string `json:"recipient"`
	Model             string `json:"model"`
	ModelConfigSHA256 string `json:"model_config_sha256"`
}
type Access struct {
	Profile   Profile
	Scope     string
	Recipient string
	Prepare   func(*http.Request, string) (Prepared, error)
	Check     func(*http.Request, Prepared) error
}
type Record struct {
	Namespace string `json:"namespace"`
	ID        string `json:"id"`
	Revision  string `json:"revision"`
}
type Prepared struct {
	Outcome   string   `json:"outcome,omitempty"`
	Query     string   `json:"-"`
	Root      string   `json:"-"`
	Recipient string   `json:"recipient"`
	Model     string   `json:"model"`
	Key       string   `json:"key"`
	View      string   `json:"authorized_view"`
	Records   []Record `json:"records"`
}
type Artifact struct {
	Name   string `json:"name"`
	Bytes  int64  `json:"bytes"`
	SHA256 string `json:"sha256"`
}
type Offer struct {
	Schema  int    `json:"schema"`
	Lease   string `json:"lease"`
	Expires int64  `json:"expires"`
	Prepared
	Artifacts []Artifact `json:"artifacts"`
}
type lease struct {
	scope string
	offer Offer
}
type Handler struct {
	Resolve          func(*http.Request) (Access, error)
	TTL              time.Duration
	MaxLeases        int
	MaxArtifactBytes int64
	MaxPreparing     int
	preparing        chan struct{}
	artifacts        map[string][]Artifact
	mu               sync.Mutex
	leases           map[string]lease
}

var denied = errors.New("native publication unavailable")

func (h *Handler) access(r *http.Request) (Access, error) {
	if h.Resolve == nil {
		return Access{}, denied
	}
	a, e := h.Resolve(r)
	if e != nil || a.Scope == "" || a.Recipient == "" || a.Prepare == nil || a.Check == nil {
		return Access{}, denied
	}
	return a, nil
}
func (h *Handler) limits() (time.Duration, int, int64) {
	ttl, n, size := h.TTL, h.MaxLeases, h.MaxArtifactBytes
	if ttl <= 0 || ttl > 5*time.Minute {
		ttl = time.Minute
	}
	if n <= 0 {
		n = 128
	}
	if size <= 0 {
		size = 1 << 30
	}
	return ttl, n, size
}
func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	fail := func(code int) { http.Error(w, "native publication unavailable", code) }
	a, e := h.access(r)
	if e != nil {
		fail(403)
		return
	}
	if r.URL.Path == "/v1/native/bootstrap" && r.Method == "GET" {
		if a.Profile.Schema != 1 || a.Profile.Recipient != a.Recipient || a.Profile.Model == "" || len(a.Profile.ModelConfigSHA256) != 64 {
			fail(503)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(a.Profile)
		return
	}
	if r.URL.Path == "/v1/native/select" && r.Method == "POST" {
		var q struct {
			Query string `json:"query"`
		}
		d := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<17))
		d.DisallowUnknownFields()
		if d.Decode(&q) != nil || d.Decode(&struct{}{}) != io.EOF || strings.TrimSpace(q.Query) == "" || len(q.Query) > 65536 {
			fail(400)
			return
		}
		h.mu.Lock()
		if h.preparing == nil {
			n := h.MaxPreparing
			if n <= 0 {
				n = 2
			}
			h.preparing = make(chan struct{}, n)
		}
		slots := h.preparing
		h.mu.Unlock()
		select {
		case slots <- struct{}{}:
			defer func() { <-slots }()
		default:
			fail(429)
			return
		}
		p, e := a.Prepare(r, q.Query)
		p.Query = q.Query
		if e != nil && os.Getenv("AIMEE_PREPARE_DIAGNOSTICS") != "" {
			log.Printf("private preparation failed: %v", e)
		}
		if e == nil && p.Outcome == "no_memory" {
			if p.Recipient != a.Recipient || p.Model == "" || p.View == "" || p.Key != "" || p.Root != "" || len(p.Records) != 0 {
				fail(503)
				return
			}
			fresh, err := h.access(r)
			if err != nil || fresh.Scope != a.Scope || fresh.Recipient != a.Recipient || fresh.Check(r, p) != nil {
				fail(403)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(struct {
				Schema    int    `json:"schema"`
				Outcome   string `json:"outcome"`
				Recipient string `json:"recipient"`
				Model     string `json:"model"`
				View      string `json:"authorized_view"`
			}{1, "no_memory", p.Recipient, p.Model, p.View})
			return
		}
		if e != nil || p.Outcome != "" || p.Recipient != a.Recipient || p.Key == "" || p.Model == "" || p.View == "" || len(p.Records) == 0 || len(p.Records) > 32 {
			fail(503)
			return
		}
		seen := map[Record]bool{}
		for _, ref := range p.Records {
			if ref.Namespace == "" || ref.ID == "" || ref.Revision == "" || seen[ref] {
				fail(503)
				return
			}
			seen[ref] = true
		}
		ttl, n, maxBytes := h.limits()
		offer := Offer{Schema: 1, Prepared: p}
		cacheKey := a.Scope + "\x00" + p.Model + "\x00" + p.Key + "\x00" + p.Root
		h.mu.Lock()
		cached := h.artifacts[cacheKey]
		h.mu.Unlock()
		offer.Artifacts = append(offer.Artifacts, cached...)
		if len(cached) == 0 {
			for _, name := range []string{"index.json", "compact.pack"} {
				f, e := os.Open(filepath.Join(p.Root, name))
				if e != nil {
					fail(503)
					return
				}
				info, e := f.Stat()
				if e != nil || !info.Mode().IsRegular() || info.Size() > maxBytes || info.Size() <= 0 {
					f.Close()
					fail(503)
					return
				}
				hash := sha256.New()
				size, e := io.Copy(hash, io.LimitReader(f, maxBytes+1))
				f.Close()
				if e != nil || size != info.Size() {
					fail(503)
					return
				}
				offer.Artifacts = append(offer.Artifacts, Artifact{name, size, hex.EncodeToString(hash.Sum(nil))})
			}
			h.mu.Lock()
			if h.artifacts == nil || len(h.artifacts) >= n {
				h.artifacts = map[string][]Artifact{}
			}
			h.artifacts[cacheKey] = append([]Artifact(nil), offer.Artifacts...)
			h.mu.Unlock()
		}
		// Renew identity/policy after preparation; never let a pre-compilation grant
		// authorize delivery after withdrawal or a policy change.
		fresh, e := h.access(r)
		if e != nil || fresh.Scope != a.Scope || fresh.Recipient != a.Recipient || fresh.Check(r, p) != nil {
			fail(403)
			return
		}
		id := make([]byte, 32)
		if _, e = rand.Read(id); e != nil {
			fail(503)
			return
		}
		offer.Lease = hex.EncodeToString(id)
		offer.Expires = time.Now().Add(ttl).Unix()
		h.mu.Lock()
		if h.leases == nil {
			h.leases = map[string]lease{}
		}
		now := time.Now().Unix()
		for k, v := range h.leases {
			if v.offer.Expires <= now {
				delete(h.leases, k)
			}
		}
		if len(h.leases) >= n {
			h.mu.Unlock()
			fail(429)
			return
		}
		h.leases[offer.Lease] = lease{a.Scope, offer}
		h.mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(offer)
		return
	}
	parts := strings.Split(strings.TrimPrefix(r.URL.Path, "/v1/native/leases/"), "/")
	if !strings.HasPrefix(r.URL.Path, "/v1/native/leases/") || len(parts) != 2 || len(parts[0]) != 64 {
		fail(404)
		return
	}
	h.mu.Lock()
	l, ok := h.leases[parts[0]]
	h.mu.Unlock()
	if !ok || l.scope != a.Scope || l.offer.Recipient != a.Recipient || time.Now().Unix() >= l.offer.Expires || a.Check(r, l.offer.Prepared) != nil {
		fail(403)
		return
	}
	if parts[1] == "approve" && r.Method == "POST" {
		w.Header().Set("Content-Type", "application/json")
		io.WriteString(w, `{"approved":true}`)
		return
	}
	if r.Method != "GET" || (parts[1] != "index.json" && parts[1] != "compact.pack") {
		fail(404)
		return
	}
	f, e := os.Open(filepath.Join(l.offer.Root, parts[1]))
	if e != nil {
		fail(503)
		return
	}
	defer f.Close()
	info, e := f.Stat()
	if e != nil {
		fail(503)
		return
	}
	// Immutable prepared files only. Verification occurs on download/admission,
	// never in attention. Final approval is mandatory before client activation.
	w.Header().Set("Content-Type", "application/octet-stream")
	http.ServeContent(w, r, parts[1], info.ModTime(), f)
}
