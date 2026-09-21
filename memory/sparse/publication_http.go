package sparse

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

// PublicationHandler is mounted BEHIND Aimee's normal authenticated API.
// resolve MUST apply its current recipient authorization and return an immutable,
// already-filtered compiled image. This callback is deliberately mandatory:
// no model-supplied identity, path, scope, or grant can choose a source image.
// Source lifetime must cover the request, as for any immutable download.
func PublicationHandler(resolve func(*http.Request) (Store, error)) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "private, no-store")
		if r.Method != "GET" || r.URL.RawQuery != "" {
			http.Error(w, "unsupported publication request", 400)
			return
		}
		if resolve == nil {
			http.Error(w, "publication unavailable", 403)
			return
		}
		src, e := resolve(r)
		if e != nil {
			http.Error(w, "publication unavailable", 403)
			return
		}
		id, e := src.Current()
		if os.IsNotExist(e) {
			w.WriteHeader(http.StatusGone)
			return
		}
		if e != nil {
			http.Error(w, "publication unavailable", 503)
			return
		}
		p, e := src.OpenPublished(id)
		if e != nil {
			http.Error(w, "publication unavailable", 503)
			return
		}
		p.Close()
		etag := `"` + id + `"`
		w.Header().Set("ETag", etag)
		// Authorization is evaluated before even a conditional response.
		if r.Header.Get("If-None-Match") == etag {
			w.WriteHeader(http.StatusNotModified)
			return
		}
		w.Header().Set("Content-Type", "application/x-tar")
		if e = src.Export(id, w); e != nil {
			panic(http.ErrAbortHandler)
		}
	})
}

// FetchPublication is publisher-side transport, never a model read API. The
// supplied client/request use the existing Aimee authenticated connection.
// Every failure withdraws the previous delivery; stale access is not a fallback.
// Downloads are staged privately, checked, and installed atomically.
func FetchPublication(ctx context.Context, client *http.Client, request *http.Request, d Delivery, gid int, maxBytes int64) (PublicationResult, error) {
	if client == nil || request == nil || maxBytes < 1024 {
		return PublicationResult{}, fmt.Errorf("publication transport configuration required")
	}
	if e := d.initialize(gid); e != nil {
		return PublicationResult{}, e
	}
	current, e := d.current()
	if e != nil {
		return PublicationResult{}, e
	}
	withdraw := func(reason string) (PublicationResult, error) {
		_, e := d.Withdraw(current)
		return PublicationResult{State: "withdrawn", Reason: reason}, e
	}
	req := request.Clone(ctx)
	req.Header = req.Header.Clone()
	req.Header.Set("If-None-Match", `"`+current+`"`)
	// Never follow redirects with publication credentials or choose a new source.
	transport := *client
	transport.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	response, e := transport.Do(req)
	if e != nil {
		return withdraw("download_failed")
	}
	defer response.Body.Close()
	if response.StatusCode == http.StatusNotModified {
		if current == "" || response.Header.Get("ETag") != `"`+current+`"` {
			return withdraw("invalid_conditional_response")
		}
		live, e := (Store{d.Root}).PinPublished(nil)
		if e != nil {
			return withdraw("local_image_invalid")
		}
		live.Close()
		_, e = d.Prune(current)
		return PublicationResult{State: "unchanged", View: current}, e
	}
	if response.StatusCode != http.StatusOK {
		return withdraw("remote_publication_unavailable")
	}
	id := strings.Trim(response.Header.Get("ETag"), `"`)
	if !digestPattern.MatchString(id) || response.ContentLength > maxBytes {
		return withdraw("invalid_download")
	}
	tmp, e := os.MkdirTemp(filepath.Dir(d.Root), ".download-")
	if e != nil {
		return withdraw("staging_unavailable")
	}
	defer os.RemoveAll(tmp)
	src := Store{filepath.Join(tmp, "image")}
	limited := &io.LimitedReader{R: response.Body, N: maxBytes + 1}
	got, e := src.Import(limited)
	// Read to EOF as well: tar permits trailing bytes, the transport budget does not.
	if e == nil {
		_, e = io.Copy(io.Discard, limited)
	}
	if e != nil || limited.N <= 0 || got != id {
		return withdraw("download_integrity_failed")
	}
	p, e := src.OpenPublished(id)
	if e != nil {
		return withdraw("uncompiled_download")
	}
	p.Close()
	if e = src.Publish(id, ""); e != nil {
		return withdraw("download_publish_failed")
	}
	result, e := d.Install(src, current, gid)
	if e != nil {
		return PublicationResult{}, e
	}
	return PublicationResult{State: "installed", View: result.View, CopiedBytes: result.CopiedBytes}, nil
}
