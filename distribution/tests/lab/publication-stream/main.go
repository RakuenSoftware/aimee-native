// Isolated test source, never a production authorization server.
package main

import (
	"context"
	"errors"
	"flag"
	"github.com/RakuenSoftware/aimee-native/memory/sparse"
	"net"
	"net/http"
	"os"
	"syscall"
	"time"
)

type peerKey struct{}

func main() {
	root := flag.String("root", "", "already scoped synthetic publication")
	socket := flag.String("socket", "", "new Unix endpoint")
	denied := flag.String("denied", "", "test withdrawal marker")
	flag.Parse()
	if *root == "" || *socket == "" || *denied == "" {
		panic("fixture arguments required")
	}
	listener, e := net.Listen("unix", *socket)
	if e != nil {
		panic(e)
	}
	defer listener.Close()
	if e = os.Chmod(*socket, 0600); e != nil {
		panic(e)
	}
	server := http.Server{ConnContext: func(ctx context.Context, c net.Conn) context.Context {
		raw, e := c.(*net.UnixConn).SyscallConn()
		if e != nil {
			return ctx
		}
		var uid uint32 = ^uint32(0)
		raw.Control(func(fd uintptr) {
			u, e := syscall.GetsockoptUcred(int(fd), syscall.SOL_SOCKET, syscall.SO_PEERCRED)
			if e == nil {
				uid = u.Uid
			}
		})
		return context.WithValue(ctx, peerKey{}, uid)
	}}
	server.Handler = sparse.PublicationStreamHandler(func(r *http.Request) (sparse.Store, error) {
		uid, ok := r.Context().Value(peerKey{}).(uint32)
		if !ok || uid != uint32(os.Geteuid()) {
			return sparse.Store{}, errors.New("fixture peer denied")
		}
		if _, e := os.Stat(*denied); !os.IsNotExist(e) {
			return sparse.Store{}, errors.New("fixture withdrawn")
		}
		return sparse.Store{Root: *root}, nil
	}, 250*time.Millisecond)
	if e = server.Serve(listener); e != nil {
		panic(e)
	}
}
