package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"github.com/RakuenSoftware/aimee-native/memory/sparse"
	"io"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"
)

type streamConnection struct{ net.Conn }

func (c streamConnection) Read(b []byte) (int, error) {
	c.SetReadDeadline(time.Now().Add(5 * time.Minute))
	return c.Conn.Read(b)
}
func (c streamConnection) Write(b []byte) (int, error) {
	c.SetWriteDeadline(time.Now().Add(30 * time.Second))
	return c.Conn.Write(b)
}

func followPublished(socket, endpoint, ca, cert, key, bearer, state, root string, gid int, out io.Writer) (err error) {
	defer func() {
		if current, e := (sparse.Store{Root: root}).Current(); e == nil {
			_, e = (sparse.Delivery{Root: root}).Withdraw(current)
			if e != nil {
				err = errors.Join(err, e)
			}
		}
	}()
	if state == "" || root == "" || state == root {
		return errors.New("separate publisher-private state and recipient root required")
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	for {
		dial := func(ctx context.Context, network, address string) (net.Conn, error) {
			c, e := (&net.Dialer{Timeout: 30 * time.Second}).DialContext(ctx, network, address)
			if e != nil {
				return nil, e
			}
			return streamConnection{c}, nil
		}
		transport := &http.Transport{DialContext: dial}
		token := ""
		url := endpoint
		if socket != "" {
			if endpoint != "" || ca != "" || cert != "" || key != "" || bearer != "" {
				return errors.New("choose existing Unix or HTTPS authentication")
			}
			transport.DialContext = func(ctx context.Context, _, _ string) (net.Conn, error) {
				return dial(ctx, "unix", socket)
			}
			url = "http://aimee/publication"
		} else {
			if !strings.HasPrefix(endpoint, "https://") {
				return errors.New("existing Aimee HTTPS identity required")
			}
			pem, e := os.ReadFile(ca)
			if e != nil {
				return e
			}
			roots := x509.NewCertPool()
			if !roots.AppendCertsFromPEM(pem) {
				return errors.New("invalid CA")
			}
			identity, e := tls.LoadX509KeyPair(cert, key)
			if e != nil {
				return e
			}
			b, e := os.ReadFile(bearer)
			if e != nil {
				return e
			}
			token = strings.TrimSpace(string(b))
			if token == "" {
				return errors.New("empty Aimee credential")
			}
			transport.TLSClientConfig = &tls.Config{MinVersion: tls.VersionTLS12, RootCAs: roots, Certificates: []tls.Certificate{identity}}
		}
		// Idle deadlines detect a wedged peer without periodically disrupting a
		// healthy continuous stream. Reconnect uses the private committed cursor.
		client := &http.Client{Transport: transport}
		req, e := http.NewRequestWithContext(ctx, "GET", url, nil)
		if e != nil {
			return e
		}
		if token != "" {
			req.Header.Set("Authorization", "Bearer "+token)
		}
		e = sparse.FollowPublication(ctx, client, req, sparse.Store{Root: state}, sparse.Delivery{Root: root}, gid, 8<<30, func(r sparse.PublicationResult) { emit(out, r) })
		client.CloseIdleConnections()
		if ctx.Err() != nil {
			return nil
		}
		if e != nil {
			if err := emit(out, map[string]string{"state": "disconnected", "reason": "publication unavailable; delivery withdrawn"}); err != nil {
				return err
			}
		}
		timer := time.NewTimer(time.Second)
		select {
		case <-ctx.Done():
			timer.Stop()
			return nil
		case <-timer.C:
		}
	}
}
