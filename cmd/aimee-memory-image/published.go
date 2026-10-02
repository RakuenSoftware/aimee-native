package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"time"

	"github.com/RakuenSoftware/aimee-qwen/memory/sparse"
)

// servePublished receives only an already-filtered recipient directory. No
// identity, grant, or permission decision is required to read local knowledge.
func servePublished(s sparse.Store, in io.Reader, out io.Writer) error {
	var current *sparse.PublishedReader
	defer func() {
		if current != nil {
			current.Close()
		}
	}()
	scanner := bufio.NewScanner(in)
	scanner.Buffer(make([]byte, 4096), 1<<20)
	ready := false
	invalidate := func() {
		ready = false
		if current != nil {
			current.Close()
			current = nil
		}
		sparse.DropPublishedCaches()
	}
	for scanner.Scan() {
		var req struct {
			Op        string
			Query     string
			Limit     int
			Proofs    []sparse.RetentionProof
			Response  json.RawMessage
			Authority string
		}
		var result any
		err := json.Unmarshal(scanner.Bytes(), &req)
		if err == nil {
			switch req.Op {
			case "pin":
				ready = false
				var next *sparse.PublishedReader
				next, err = s.PinPublished(current)
				if err == nil && next != current {
					if current != nil {
						current.Close()
					}
					current = next
				} else if err != nil {
					invalidate()
				}
				if err == nil {
					ready = true
					result = map[string]string{"view": current.View.ID, "publication": current.Publication}
				}
			case "check":
				var id string
				id, err = s.Current()
				if err != nil {
					invalidate()
				}
				if err == nil {
					result = map[string]string{"view": id}
				}
			case "retain":
				if !ready || len(req.Proofs) > 10000 {
					err = fmt.Errorf("invalid retention check")
				} else {
					result = map[string]any{"view": current.View.ID, "retained": current.Retain(req.Proofs, time.Now())}
				}
			case "search_restriction", "authorize_response", "resolve_response", "resolve_local_response":
				var id string
				id, err = s.Current()
				if err != nil {
					invalidate()
				}
				if err == nil && (!ready || id != current.View.ID) {
					err = fmt.Errorf("published generation changed")
				}
				if err == nil {
					if req.Op == "search_restriction" {
						result, err = current.RestrictRemote(req.Authority)
					} else {
						var refs []sparse.Ref
						if req.Op == "resolve_local_response" {
							refs, err = current.ResolveLocal(req.Response, time.Now())
						} else {
							refs, err = current.ResolveRemote(req.Response, time.Now())
						}
						if err == nil {
							result = map[string]any{"refs": refs, "authorized": current.Publication, "authorization": current.Publication, "view": current.View.ID}
						}
					}
				}
			case "recall":
				if !ready {
					err = fmt.Errorf("snapshot is not pinned")
				} else {
					result, err = current.Recall(req.Query, req.Limit, req.Authority, time.Now())
				}
			default:
				err = fmt.Errorf("unsupported operation")
			}
		}
		if err != nil {
			result = map[string]string{"error": err.Error()}
		}
		if err = emit(out, result); err != nil {
			return err
		}
	}
	return scanner.Err()
}
