// aimee-memory-read is a restricted Unix ingress to Aimee's memory module.
// The socket is owner-only. Its caller must already enforce an Aimee release
// grant and verify egress; restriction IDs are a narrowing filter, not a grant.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/JBailes/aimee/server-go/bus"
	"github.com/JBailes/aimee/server-go/modules/memory"
)

type searchRequest struct {
	Keywords    []string                  `json:"keywords"`
	Limit       int                       `json:"limit"`
	Restriction *memory.SearchRestriction `json:"restriction"`
}
type dataCall func(context.Context, []byte) ([]byte, error)

func searchHandler(namespace string, call dataCall) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fail := func(status int) {
			w.WriteHeader(status)
			_, _ = io.WriteString(w, `{"error":"restricted read unavailable"}`)
		}
		if r.Method != "POST" || r.URL.Path != "/v1/memory/search" {
			fail(403)
			return
		}
		d := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20))
		d.DisallowUnknownFields()
		var q searchRequest
		if d.Decode(&q) != nil || d.Decode(&struct{}{}) != io.EOF || q.Restriction.Validate() != nil || q.Restriction.Namespace != namespace || len(q.Keywords) < 1 || len(q.Keywords) > 16 || q.Limit < 1 || q.Limit > 32 {
			fail(400)
			return
		}
		for _, k := range q.Keywords {
			if strings.TrimSpace(k) == "" {
				fail(400)
				return
			}
		}
		query := strings.Join(q.Keywords, " ")
		if len(query) > 16384 {
			fail(400)
			return
		}
		payload, _ := json.Marshal(memory.DataRequest{Operation: "search-restricted", Query: query, Limit: q.Limit, Scope: memory.Scope{Type: memory.ScopeUser, Value: "_user"}, Restriction: q.Restriction})
		raw, err := call(r.Context(), payload)
		if err != nil {
			fail(503)
			return
		}
		var result memory.DataResponse
		replyDecoder := json.NewDecoder(bytes.NewReader(raw))
		replyDecoder.DisallowUnknownFields()
		if replyDecoder.Decode(&result) != nil || replyDecoder.Decode(&struct{}{}) != io.EOF {
			fail(503)
			return
		}
		if result.Records == nil {
			result.Records = []memory.Record{}
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"status": "ok", "facts": result.Records, "windows": []any{}, "active_context_missing": false, "restriction": q.Restriction})
	})
}
func run() error {
	socket := flag.String("socket", "", "new owner-only Unix socket")
	busPath := flag.String("bus", "", "existing Aimee module bus")
	namespace := flag.String("namespace", "", "authoritative namespace of this server's memory store")
	principal := flag.Uint("principal", 0, "explicitly granted module-bus principal")
	flag.Parse()
	if *socket == "" || *busPath == "" || *namespace == "" || *principal == 0 || *principal > 4294967295 {
		return errors.New("socket, bus, namespace and granted principal required")
	}
	if _, err := os.Lstat(*socket); !os.IsNotExist(err) {
		return errors.New("socket path must not exist")
	}
	client, err := bus.ConnectClient(context.Background(), *busPath, 1, uint32(*principal))
	if err != nil {
		return err
	}
	defer client.Detach()
	caller, err := bus.NewConcurrentModuleCaller(context.Background(), client)
	if err != nil {
		return err
	}
	defer caller.CloseAndWait()
	listener, err := net.Listen("unix", *socket)
	if err != nil {
		return err
	}
	defer listener.Close()
	defer os.Remove(*socket)
	if err = os.Chmod(*socket, 0600); err != nil {
		return err
	}
	call := func(ctx context.Context, raw []byte) ([]byte, error) {
		return caller.Call(ctx, memory.EventData, memory.StageData, 0, 30*time.Second, raw)
	}
	server := http.Server{Handler: searchHandler(*namespace, call), ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 35 * time.Second, WriteTimeout: 35 * time.Second, IdleTimeout: 30 * time.Second, MaxHeaderBytes: 8192}
	return server.Serve(listener)
}
func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
