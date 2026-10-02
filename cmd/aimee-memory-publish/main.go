// Aimee's local publication service. Runs under the Aimee control-plane identity,
// outside the model sandbox. Unix peer credentials authenticate the consumer;
// execution-policy explicitly releases exact records and their future revisions.
package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	store "github.com/JBailes/aimee/server-go/modules/aimee"
	policy "github.com/JBailes/aimee/server-go/modules/execution-policy"
	"github.com/JBailes/aimee/server-go/modules/memory"
	"github.com/RakuenSoftware/aimee-qwen/aimeeexport"
	"github.com/RakuenSoftware/aimee-qwen/memory/sparse"
	"github.com/jackc/pgx/v5"
	"io"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"sync"
	"syscall"
	"time"
)

type txQuery struct{ pgx.Tx }

func (q txQuery) Query(c context.Context, s string, a ...any) (store.Rows, error) {
	return q.Tx.Query(c, s, a...)
}
func (q txQuery) QueryRow(c context.Context, s string, a ...any) store.Row {
	return q.Tx.QueryRow(c, s, a...)
}

func (q txQuery) Exec(c context.Context, s string, a ...any) (store.Tag, error) {
	return q.Tx.Exec(c, s, a...)
}

type uidKey struct{}
type publisher struct {
	sync.Mutex
	policyPath, recipient, dsn, authority, serverName string
	base, out                                         sparse.Store
	last, lastRelease                                 string
}

func readPolicy(path string) (policy.MemoryReleasePolicy, []byte, error) {
	var p policy.MemoryReleasePolicy

	fd, e := syscall.Open(path, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if e != nil {
		return p, nil, e
	}
	file := os.NewFile(uintptr(fd), path)
	defer file.Close()
	info, e := file.Stat()
	if e != nil {
		return p, nil, e
	}
	if !info.Mode().IsRegular() || info.Mode().Perm()&0022 != 0 || info.Sys().(*syscall.Stat_t).Uid != uint32(os.Geteuid()) || info.Size() > 4<<20 {
		return p, nil, errors.New("release policy must be bounded and control-plane-owned")
	}
	raw, e := io.ReadAll(io.LimitReader(file, 4<<20+1))
	if e != nil {
		return p, nil, e
	}
	if len(raw) > 4<<20 {
		return p, nil, errors.New("release policy too large")
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if e = decoder.Decode(&p); e != nil {
		return p, nil, e
	}
	if e = decoder.Decode(&struct{}{}); e != io.EOF {
		return p, nil, errors.New("invalid policy document")
	}
	return p, raw, nil
}
func (p *publisher) resolve(r *http.Request) (result sparse.Store, err error) {
	stage := "authentication"
	defer func() {
		if err != nil {
			fmt.Fprintf(os.Stderr, "publication unavailable phase=%s\n", stage)
		}
	}()
	p.Lock()
	defer p.Unlock()
	uid, ok := r.Context().Value(uidKey{}).(uint32)
	if !ok {
		return sparse.Store{}, errors.New("authenticated Unix peer required")
	}
	release, raw, e := readPolicy(p.policyPath)
	if e != nil {
		return sparse.Store{}, e
	}
	now := time.Now().UTC()
	if e = release.Validate(p.recipient, uid, now); e != nil {
		return sparse.Store{}, e
	}
	// Withdraw the old recipient image before spending time compiling a new
	// policy. The consumer reconnects after processing this denial barrier.
	digest := release.Digest()
	if p.lastRelease != "" && p.lastRelease != digest {
		p.lastRelease = digest
		return sparse.Store{}, errors.New("release changed; withdraw before republishing")
	}
	p.lastRelease = digest
	stage = "source_snapshot"
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	config, e := pgx.ParseConfig(p.dsn)
	if e != nil {
		return sparse.Store{}, errors.New("invalid memory source connection")
	}
	if p.serverName != "" {
		if config.TLSConfig == nil || config.TLSConfig.InsecureSkipVerify {
			return sparse.Store{}, errors.New("verified database TLS required")
		}
		config.TLSConfig.ServerName = p.serverName
	}
	conn, e := pgx.ConnectConfig(ctx, config)
	if e != nil {
		return sparse.Store{}, errors.New("memory source unavailable")
	}
	defer conn.Close(ctx)
	tx, e := conn.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly})
	if e != nil {
		return sparse.Store{}, e
	}
	defer tx.Rollback(ctx)
	ids := []string{}
	for _, rule := range release.Records {
		ids = append(ids, rule.ID)
	}
	stage = "source_export"
	rows, e := aimeeexport.ExportSparseRecordsSelected(ctx, txQuery{tx}, memory.PlacementServer, memory.Scope{Type: "user", Value: "_user"}, release.Namespace, ids)
	if e != nil {
		return sparse.Store{}, e
	}
	records := []sparse.Record{}
	cues := []sparse.ReferenceCue{}
	for _, row := range rows {
		if !release.Allows(row.Namespace, row.ID, row.Revision, row.Scope.Type, row.Scope.Value) || row.Lifecycle != "active" || row.Suppressed || row.Redirect != nil {
			continue
		}
		if row.ValidFrom != "" {
			t, e := time.Parse(time.RFC3339Nano, row.ValidFrom)
			if e != nil || now.Before(t) {
				continue
			}
		}
		if row.ValidUntil != "" {
			t, e := time.Parse(time.RFC3339Nano, row.ValidUntil)
			if e != nil || !now.Before(t) {
				continue
			}
		}
		records = append(records, sparse.ServingRecord(row))
		for _, rule := range release.Records {
			if rule.ID == row.ID {
				for _, cue := range rule.Cues {
					cues = append(cues, sparse.ReferenceCue{Ref: row.Ref, Cue: cue, Authority: p.authority})
				}
			}
		}
	}
	if e = tx.Commit(ctx); e != nil {
		return sparse.Store{}, e
	}
	state, _ := json.Marshal([]any{release.Digest(), records, cues})
	sum := sha256.Sum256(state)
	binding := hex.EncodeToString(sum[:])
	if binding != p.last {
		stage = "compile_release"
		head, e := p.out.CompileReleased(p.base, release.BaseView, binding, release.Namespace, p.authority, records, cues, now)
		if e != nil {
			return sparse.Store{}, e
		}
		// Validate serving invariants before advertising the new generation. A
		// structurally valid manifest can still contain unusable retrieval cues.
		stage = "validate_release"
		reader, e := p.out.OpenPublished(head)
		if e != nil {
			return sparse.Store{}, e
		}
		reader.Close()
		stage = "commit_release"
		check, _, e := readPolicy(p.policyPath)
		if e != nil || check.Digest() != release.Digest() || check.Validate(p.recipient, uid, time.Now().UTC()) != nil {
			return sparse.Store{}, errors.New("release changed during publication")
		}
		latest, e := os.ReadFile(p.policyPath)
		if e != nil || !bytes.Equal(latest, raw) {
			return sparse.Store{}, errors.New("release changed during publication")
		}
		old, e := p.out.Current()
		if e != nil && !os.IsNotExist(e) {
			return sparse.Store{}, e
		}
		if e = p.out.Publish(head, old); e != nil {
			return sparse.Store{}, e
		}
		if e = os.WriteFile(filepath.Join(p.out.Root, "RELEASE"), []byte(release.Digest()), 0600); e != nil {
			return sparse.Store{}, e
		}
		if e = p.out.RememberPublication(head); e != nil {
			return sparse.Store{}, e
		}
		p.last = binding
		fmt.Fprintf(os.Stderr, "published view=%s records=%d\n", head, len(records))
	}
	return p.out, nil
}
func run() error {
	socket := flag.String("socket", "", "new owner-only Aimee publication socket")
	release := flag.String("release-policy", "", "server-owned exact-resource release policy")
	recipient := flag.String("recipient", "", "configured recipient; never accepted from requests")
	base := flag.String("base", "", "approved immutable general KB snapshot")
	root := flag.String("root", "", "publisher-private history directory")
	serverName := flag.String("database-server-name", "", "verified TLS database name when dialing a fixed IP")
	authority := flag.String("read-authority", "test", "compiled retrieval authority label")
	historyKeep := flag.Int("history-keep", 64, "private resume checkpoints retained by background compaction")
	compactInterval := flag.Duration("compact-interval", time.Minute, "background private history compaction interval")
	interval := flag.Duration("interval", time.Second, "live source reconciliation interval")
	flag.Parse()
	if *socket == "" || *release == "" || *recipient == "" || *base == "" || *root == "" || *interval < 100*time.Millisecond || *historyKeep < 2 || *compactInterval < time.Second {
		return errors.New("publication configuration required")
	}
	if _, e := os.Lstat(*socket); !os.IsNotExist(e) {
		return errors.New("socket must not exist")
	}
	dsn := os.Getenv("AIMEE_IMAGE_DATABASE_URL")
	if dsn == "" {
		return errors.New("Aimee read-only source connection required")
	}
	if e := os.MkdirAll(*root, 0700); e != nil {
		return e
	}
	if e := os.Chmod(*root, 0700); e != nil {
		return e
	}
	// A private history directory belongs to one recipient forever. Policy changes
	// cannot repurpose another model's resume cursor or publisher history.
	identity := filepath.Join(*root, "RECIPIENT")
	if b, e := os.ReadFile(identity); e == nil {
		if string(b) != *recipient {
			return errors.New("publisher recipient mismatch")
		}
	} else if os.IsNotExist(e) {
		if e = os.WriteFile(identity, []byte(*recipient), 0600); e != nil {
			return e
		}
	} else {
		return e
	}
	p := &publisher{policyPath: *release, recipient: *recipient, dsn: dsn, authority: *authority, serverName: *serverName, base: sparse.Store{Root: *base}, out: sparse.Store{Root: *root}}
	if previous, e := os.ReadFile(filepath.Join(*root, "RELEASE")); e == nil {
		p.lastRelease = string(previous)
	} else if !os.IsNotExist(e) {
		return e
	}
	listener, e := net.Listen("unix", *socket)
	if e != nil {
		return e
	}
	defer listener.Close()
	defer os.Remove(*socket)
	if e = os.Chmod(*socket, 0600); e != nil {
		return e
	}
	server := http.Server{ReadHeaderTimeout: 5 * time.Second, MaxHeaderBytes: 8192, ConnContext: func(ctx context.Context, c net.Conn) context.Context {
		u, ok := c.(*net.UnixConn)
		if !ok {
			return ctx
		}
		raw, e := u.SyscallConn()
		if e != nil {
			return ctx
		}
		var cred *syscall.Ucred
		raw.Control(func(fd uintptr) { cred, _ = syscall.GetsockoptUcred(int(fd), syscall.SOL_SOCKET, syscall.SO_PEERCRED) })
		if cred == nil {
			return ctx
		}
		return context.WithValue(ctx, uidKey{}, cred.Uid)
	}, Handler: sparse.PublicationStreamHandler(p.resolve, *interval)}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	go func() { <-ctx.Done(); server.Close() }()
	go func() {
		ticker := time.NewTicker(*compactInterval)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				p.Lock()
				n, err := p.out.CompactPublicationHistory(*historyKeep)
				p.Unlock()
				if err != nil && !os.IsNotExist(err) {
					fmt.Fprintln(os.Stderr, "history compaction unavailable")
				} else if n > 0 {
					fmt.Fprintf(os.Stderr, "history compacted objects=%d\n", n)
				}
			}
		}
	}()
	e = server.Serve(listener)
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
