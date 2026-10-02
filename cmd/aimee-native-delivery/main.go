// Private native-memory delivery. TLS, bearer and certificate grant validation
// stay in Aimee's existing frontend; this process listens only on a private UDS.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	native "github.com/RakuenSoftware/aimee-qwen/memory/nativepublication"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"
)

func run() error {
	socket := flag.String("socket", "", "private Unix socket")
	bindings := flag.String("bindings", "", "operator-owned account/release bindings")
	uid := flag.Uint("frontend-uid", uint(os.Geteuid()), "kernel uid of Aimee frontend")
	flag.Parse()
	if *socket == "" || *bindings == "" || uint64(*uid) > uint64(^uint32(0)) {
		return errors.New("socket, bindings and valid frontend uid required")
	}
	dir, e := os.Stat(filepath.Dir(*socket))
	if e != nil {
		return e
	}
	if !dir.IsDir() || dir.Mode().Perm()&0077 != 0 || dir.Sys().(*syscall.Stat_t).Uid != uint32(os.Geteuid()) {
		return errors.New("socket directory must be private and service-owned")
	}
	// Never unlink an existing listener. The service supervisor owns stale-socket
	// cleanup and must first establish that the previous process has exited.
	l, e := net.Listen("unix", *socket)
	if e != nil {
		return e
	}
	defer l.Close()
	if e = os.Chmod(*socket, 0600); e != nil {
		return e
	}
	authority := native.Authority{Bindings: *bindings, FrontendUID: uint32(*uid)}
	server := http.Server{Handler: &native.Handler{Resolve: authority.Resolve}, ConnContext: native.PeerContext, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 15 * time.Second, WriteTimeout: 11 * time.Minute, IdleTimeout: 5 * time.Second, MaxHeaderBytes: 8192}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	go func() { <-ctx.Done(); server.Close() }()
	e = server.Serve(l)
	if errors.Is(e, http.ErrServerClosed) {
		return nil
	}
	return e
}
func main() {
	if e := run(); e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
}
