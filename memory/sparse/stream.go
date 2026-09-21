package sparse

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"time"
)

type PublicationFrame struct {
	Version int               `json:"version"`
	State   string            `json:"state"`
	View    string            `json:"view,omitempty"`
	Delta   *PublicationDelta `json:"delta,omitempty"`
}

// PublicationStreamHandler uses the application's authenticated resolver on every
// iteration, including heartbeat and resume. An identity/path from the wire is
// never a source selector. Source history stays publisher-private.
func PublicationStreamHandler(resolve func(*http.Request) (Store, error), interval time.Duration) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// A staged receiver rechecks the authenticated release immediately before
		// exposing bytes. A queued frame is not permission to commit after revocation.
		if r.Method == "HEAD" && r.URL.RawQuery == "" && resolve != nil {
			src, e := resolve(r)
			if e != nil {
				w.WriteHeader(http.StatusForbidden)
				return
			}
			id, e := src.Current()
			if e != nil || !digestPattern.MatchString(r.Header.Get("X-Aimee-View")) || id != r.Header.Get("X-Aimee-View") {
				w.WriteHeader(http.StatusPreconditionFailed)
				return
			}
			w.Header().Set("X-Aimee-View", id)
			w.Header().Set("Cache-Control", "private, no-store")
			w.WriteHeader(http.StatusOK)
			return
		}
		if r.Method != "GET" || r.URL.RawQuery != "" || resolve == nil || interval <= 0 {
			http.Error(w, "publication unavailable", 403)
			return
		}
		f, ok := w.(http.Flusher)
		if !ok {
			http.Error(w, "streaming unavailable", 503)
			return
		}
		base := r.Header.Get("Last-Event-ID")
		if base != "" && !digestPattern.MatchString(base) {
			http.Error(w, "invalid cursor", 400)
			return
		}
		w.Header().Set("Content-Type", "application/x-ndjson")
		w.Header().Set("Cache-Control", "private, no-store")
		enc := json.NewEncoder(w)
		var previous *PublishedReader
		defer func() {
			if previous != nil {
				previous.Close()
			}
		}()
		for {
			if r.Context().Err() != nil {
				return
			}
			src, e := resolve(r)
			if e != nil {
				enc.Encode(PublicationFrame{Version: 1, State: "withdrawn"})
				f.Flush()
				return
			}
			id, e := src.Current()
			if e != nil {
				enc.Encode(PublicationFrame{Version: 1, State: "withdrawn"})
				f.Flush()
				return
			}
			if previous == nil && base != "" {
				previous, _ = src.OpenPublished(base)
			}
			if base == id && previous != nil {
				if e = enc.Encode(PublicationFrame{Version: 1, State: "unchanged", View: id}); e != nil {
					return
				}
			} else {
				next, e := src.OpenPublished(id)
				if e != nil {
					return
				}
				d, e := DiffPublished(previous, next)
				if e != nil {
					next.Close()
					return
				}
				// Recheck release after preparing the payload. Changed policy may have
				// removed records while a large bootstrap was being assembled.
				check, e := resolve(r)
				if e != nil {
					next.Close()
					enc.Encode(PublicationFrame{Version: 1, State: "withdrawn"})
					f.Flush()
					return
				}
				current, e := check.Current()
				if e != nil {
					next.Close()
					return
				}
				if current != id {
					next.Close()
					continue
				}
				if e = enc.Encode(PublicationFrame{Version: 1, State: "delta", View: id, Delta: &d}); e != nil {
					next.Close()
					return
				}
				if previous != nil {
					previous.Close()
				}
				previous = next
				base = id
			}
			f.Flush()
			timer := time.NewTimer(interval)
			select {
			case <-r.Context().Done():
				timer.Stop()
				return
			case <-timer.C:
			}
		}
	})
}

// FollowPublication consumes one connection. The caller reconnects using the
// private committed state. No incomplete transaction advances either CURRENT.
// All connection/authorization failures withdraw model-facing bytes. The private
// publisher-owned state permits resumption without retaining stale model access.
func FollowPublication(ctx context.Context, client *http.Client, request *http.Request, state Store, d Delivery, gid int, maxBytes int64, onCommit func(PublicationResult)) (err error) {
	if client == nil || request == nil || maxBytes < 1024 || state.Root == d.Root {
		return fmt.Errorf("invalid stream configuration")
	}
	if e := os.MkdirAll(state.Root, 0700); e != nil {
		return e
	}
	if e := os.Chmod(state.Root, 0700); e != nil {
		return e
	}
	mirror := Delivery{filepath.Join(state.Root, "committed")}
	if e := mirror.initialize(-1); e != nil {
		return e
	}
	if e := d.initialize(gid); e != nil {
		return e
	}
	defer func() {
		if err != nil {
			if id, e := d.current(); e == nil {
				_, we := d.Withdraw(id)
				if we != nil {
					err = fmt.Errorf("stream failed; withdrawal failed: %w", we)
				}
			}
		}
	}()
	cursor, e := mirror.current()
	if e != nil {
		return e
	}
	req := request.Clone(ctx)
	req.Header = req.Header.Clone()
	req.Header.Set("Last-Event-ID", cursor)
	transport := *client
	transport.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	response, e := transport.Do(req)
	if e != nil {
		return e
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return fmt.Errorf("publication stream rejected: %d", response.StatusCode)
	}
	scanner := bufio.NewScanner(response.Body)
	scanner.Buffer(make([]byte, 65536), int(maxBytes))
	for {
		if !scanner.Scan() {
			if scanner.Err() != nil {
				return scanner.Err()
			}
			return fmt.Errorf("publication stream ended")
		}
		if int64(len(scanner.Bytes())) > maxBytes {
			return fmt.Errorf("publication frame too large")
		}
		decoder := json.NewDecoder(bytes.NewReader(scanner.Bytes()))
		decoder.DisallowUnknownFields()
		var frame PublicationFrame
		if e = decoder.Decode(&frame); e != nil {
			return e
		}
		if e = decoder.Decode(&struct{}{}); e != io.EOF {
			return fmt.Errorf("invalid trailing frame data")
		}
		if frame.Version != 1 {
			return fmt.Errorf("unsupported stream version")
		}
		applyStarted := time.Now()
		switch frame.State {
		case "withdrawn":
			return fmt.Errorf("publication withdrawn")
		case "delta":
			if frame.Delta == nil || frame.Delta.Target != frame.View {
				return fmt.Errorf("invalid delta frame")
			}
			if frame.Delta.Base == "" && cursor != "" {
				// Server history was compacted: reset private staging only, then install a
				// complete authorized snapshot. The live delivery changes only at commit.
				if _, e = mirror.Withdraw(cursor); e != nil {
					return e
				}
				cursor = ""
			}
			if _, e = mirror.ApplyDelta(*frame.Delta, -1); e != nil {
				return e
			}
			cursor = frame.View
		case "unchanged":
			if frame.Delta != nil || cursor == "" || frame.View != cursor {
				return fmt.Errorf("invalid heartbeat")
			}
		default:
			return fmt.Errorf("invalid stream state")
		}
		current, e := d.current()
		if e != nil {
			return e
		}
		if current != cursor {
			src := Store{filepath.Join(mirror.Root, "snapshots", cursor)}
			result, e := d.install(src, current, gid, func() error {
				check := request.Clone(ctx)
				check.Method = "HEAD"
				check.Body = nil
				check.ContentLength = 0
				check.Header = request.Header.Clone()
				check.Header.Set("X-Aimee-View", cursor)
				approved, e := transport.Do(check)
				if e != nil {
					return e
				}
				defer approved.Body.Close()
				if approved.StatusCode != http.StatusOK || approved.Header.Get("X-Aimee-View") != cursor {
					return fmt.Errorf("publication no longer approved at commit")
				}
				return nil
			})
			if e != nil {
				return e
			}
			if onCommit != nil {
				metric := PublicationResult{State: "installed", View: cursor, CopiedBytes: result.CopiedBytes, TransferredBytes: int64(len(scanner.Bytes()) + 1), ReusedBytes: result.ReusedBytes, ApplyMillis: float64(time.Since(applyStarted).Microseconds()) / 1000}
				if frame.Delta != nil {
					for _, layer := range frame.Delta.Layers {
						metric.Upserts += len(layer.Upsert)
						metric.Removals += len(layer.Remove)
						metric.CueEdits += len(layer.CueInsert) + len(layer.CueRemove)
					}
				}
				onCommit(metric)
			}
		}
	}
}
