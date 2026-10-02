// Isolated HTTPS/mTLS transport fixture. Synthetic credentials never represent
// production enrollment; native artifact bytes may come from a real preparation.
package main

import (
	"crypto/sha256"
	"crypto/subtle"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	native "github.com/RakuenSoftware/aimee-qwen/memory/nativepublication"
	"log"
	"net/http"
	"os"
	"strings"
	"time"
)

func main() {
	template := flag.String("preparation-template", "", "optional actual private preparation template")
	binary := flag.String("native-prepare", "", "private Rust preparer")
	result := flag.String("prepared", "", "native-prepare result JSON")
	modelConfig := flag.String("model-config", "", "model config")
	tokenFile := flag.String("token-file", "", "synthetic credential file")
	cert := flag.String("cert", "", "TLS certificate")
	key := flag.String("key", "", "TLS key")
	ca := flag.String("client-ca", "", "client CA")
	deny := flag.String("deny", "", "denial marker")
	denyApprove := flag.String("deny-approve", "", "final approval denial marker")
	listen := flag.String("listen", "127.0.0.1:8445", "lab listener")
	flag.Parse()
	raw, e := os.ReadFile(*result)
	if e != nil {
		log.Fatal(e)
	}
	var p struct {
		Root      string          `json:"root"`
		Recipient string          `json:"recipient"`
		Model     string          `json:"model"`
		Key       string          `json:"key"`
		View      string          `json:"authorized_view"`
		Records   []native.Record `json:"records"`
	}
	if e = json.Unmarshal(raw, &p); e != nil {
		log.Fatal(e)
	}
	token, e := os.ReadFile(*tokenFile)
	if e != nil {
		log.Fatal(e)
	}
	token = []byte(strings.TrimSpace(string(token)))
	cfg, e := os.ReadFile(*modelConfig)
	if e != nil {
		log.Fatal(e)
	}
	hash := sha256.Sum256(cfg)
	pem, e := os.ReadFile(*ca)
	if e != nil {
		log.Fatal(e)
	}
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(pem) {
		log.Fatal("invalid CA")
	}
	denied := func() bool { _, e := os.Stat(*deny); return e == nil }
	prepared := native.Prepared{Root: p.Root, Recipient: p.Recipient, Model: p.Model, Key: p.Key, View: p.View, Records: p.Records}
	handler := &native.Handler{TTL: time.Minute, Resolve: func(r *http.Request) (native.Access, error) {
		if denied() || subtle.ConstantTimeCompare([]byte(r.Header.Get("Authorization")), append([]byte("Bearer "), token...)) != 1 {
			return native.Access{}, errors.New("denied")
		}
		if *template != "" {
			real := native.Preparer{Binary: *binary, Template: *template, Profile: native.Profile{Schema: 1, Recipient: p.Recipient, Model: p.Model, ModelConfigSHA256: hex.EncodeToString(hash[:])}}
			access, e := real.Access("synthetic-transport-fixture", p.Recipient)
			if e != nil {
				return access, e
			}
			check := access.Check
			access.Check = func(r *http.Request, v native.Prepared) error {
				_, blocked := os.Stat(*denyApprove)
				if denied() || (strings.HasSuffix(r.URL.Path, "/approve") && blocked == nil) {
					return errors.New("denied")
				}
				return check(r, v)
			}
			return access, nil
		}
		return native.Access{Scope: "synthetic-transport-fixture", Recipient: p.Recipient,
			Profile: native.Profile{Schema: 1, Recipient: p.Recipient, Model: p.Model, ModelConfigSHA256: hex.EncodeToString(hash[:])},
			Prepare: func(*http.Request, string) (native.Prepared, error) { return prepared, nil },
			Check: func(r *http.Request, got native.Prepared) error {
				_, blocked := os.Stat(*denyApprove)
				if denied() || (strings.HasSuffix(r.URL.Path, "/approve") && blocked == nil) || got.Key != p.Key {
					return errors.New("denied")
				}
				return nil
			},
		}, nil
	}}
	server := http.Server{Addr: *listen, Handler: handler, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 10 * time.Second, WriteTimeout: 10 * time.Minute, IdleTimeout: 30 * time.Second, MaxHeaderBytes: 8192, TLSConfig: &tls.Config{MinVersion: tls.VersionTLS12, ClientAuth: tls.RequireAndVerifyClientCert, ClientCAs: pool}}
	log.Fatal(server.ListenAndServeTLS(*cert, *key))
}
