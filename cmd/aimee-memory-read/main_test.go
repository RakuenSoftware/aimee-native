package main

import (
	"context"
	"encoding/json"
	"errors"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/JBailes/aimee/server-go/modules/memory"
)

func TestRestrictedIngress(t *testing.T) {
	r := memory.SearchRestriction{Version: 1, Namespace: "server", Authorization: strings.Repeat("a", 64), IDs: []int64{5, 6}}
	for _, tc := range []struct {
		name    string
		body    any
		failure bool
		status  int
	}{
		{"ok", searchRequest{[]string{"noisy query"}, 2, &r}, false, 200},
		{"upstream failure", searchRequest{[]string{"query"}, 2, &r}, true, 503},
		{"no restriction", map[string]any{"keywords": []string{"query"}, "limit": 2}, false, 400},
		{"bad limit", searchRequest{[]string{"query"}, 33, &r}, false, 400},
		{"empty query", searchRequest{[]string{" "}, 2, &r}, false, 400},
		{"extra field", map[string]any{"keywords": []string{"query"}, "limit": 2, "restriction": r, "write": true}, false, 400},
	} {
		t.Run(tc.name, func(t *testing.T) {
			calls := 0
			h := searchHandler("server", func(_ context.Context, b []byte) ([]byte, error) {
				calls++
				var req memory.DataRequest
				if err := json.Unmarshal(b, &req); err != nil {
					t.Fatal(err)
				}
				if req.Operation != "search-restricted" || req.Restriction == nil || len(req.Restriction.IDs) != 2 || req.Limit != 2 {
					t.Fatalf("bad request: %s", b)
				}
				if tc.failure {
					return nil, errors.New("unavailable")
				}
				return []byte(`{"records":[]}`), nil
			})
			b, _ := json.Marshal(tc.body)
			w := httptest.NewRecorder()
			h.ServeHTTP(w, httptest.NewRequest("POST", "/v1/memory/search", strings.NewReader(string(b))))
			if w.Code != tc.status {
				t.Fatalf("%d: %s", w.Code, w.Body.String())
			}
			if tc.status == 400 && calls != 0 {
				t.Fatal("invalid request reached module")
			}
			if tc.status == 200 {
				var body map[string]any
				_ = json.Unmarshal(w.Body.Bytes(), &body)
				if body["restriction"] == nil || body["facts"] == nil {
					t.Fatal("unbound empty response")
				}
			}
		})
	}
	t.Run("namespace is server controlled", func(t *testing.T) {
		b, _ := json.Marshal(searchRequest{[]string{"query"}, 2, &r})
		w := httptest.NewRecorder()
		searchHandler("another", func(context.Context, []byte) ([]byte, error) {
			t.Fatal("wrong namespace reached module")
			return nil, nil
		}).ServeHTTP(w, httptest.NewRequest("POST", "/v1/memory/search", strings.NewReader(string(b))))
		if w.Code != 400 {
			t.Fatal(w.Code)
		}
	})
}

func TestModuleErrorCannotBecomeAuthorizedMiss(t *testing.T) {
	r := memory.SearchRestriction{Version: 1, Namespace: "server", Authorization: strings.Repeat("a", 64), IDs: []int64{5}}
	b, _ := json.Marshal(searchRequest{[]string{"query"}, 2, &r})
	h := searchHandler("server", func(context.Context, []byte) ([]byte, error) {
		return []byte(`{"status":"error","message":"denied"}`), nil
	})
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest("POST", "/v1/memory/search", strings.NewReader(string(b))))
	if w.Code != 503 || strings.Contains(w.Body.String(), "restriction") {
		t.Fatalf("error became bound miss: %s", w.Body.String())
	}
}
