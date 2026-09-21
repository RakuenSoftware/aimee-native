package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/RakuenSoftware/aimee-qwen/memory/sparse"
)

func fetchPublication(ctx context.Context, endpoint, ca, cert, key, bearer, root string, gid int) (out sparse.PublicationResult, err error) {
	defer func() {
		if err != nil {
			if current, e := (sparse.Store{Root: root}).Current(); e == nil {
				if _, e = (sparse.Delivery{Root: root}).Withdraw(current); e != nil {
					err = errors.Join(err, e)
				}
			}
		}
	}()
	if !strings.HasPrefix(endpoint, "https://") || ca == "" || cert == "" || key == "" || bearer == "" {
		return sparse.PublicationResult{}, errors.New("existing Aimee HTTPS identity required")
	}
	pem, e := os.ReadFile(ca)
	if e != nil {
		return sparse.PublicationResult{}, e
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(pem) {
		return sparse.PublicationResult{}, errors.New("invalid Aimee CA")
	}
	identity, e := tls.LoadX509KeyPair(cert, key)
	if e != nil {
		return sparse.PublicationResult{}, e
	}
	token, e := os.ReadFile(bearer)
	if e != nil {
		return sparse.PublicationResult{}, e
	}
	if strings.TrimSpace(string(token)) == "" {
		return sparse.PublicationResult{}, errors.New("empty Aimee credential")
	}
	client := &http.Client{Timeout: 5 * time.Minute, Transport: &http.Transport{TLSClientConfig: &tls.Config{MinVersion: tls.VersionTLS12, RootCAs: roots, Certificates: []tls.Certificate{identity}}}}
	defer client.CloseIdleConnections()
	request, e := http.NewRequestWithContext(ctx, "GET", endpoint, nil)
	if e != nil {
		return sparse.PublicationResult{}, e
	}
	request.Header.Set("Authorization", "Bearer "+strings.TrimSpace(string(token)))
	return sparse.FetchPublication(ctx, client, request, sparse.Delivery{Root: root}, gid, 8<<30)
}
