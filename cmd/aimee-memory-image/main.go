// aimee-memory-image builds and reads local sparse memory artifacts. It never
// mutates authoritative Aimee databases; export-postgres uses a read-only snapshot.
package main

import (
	"bufio"
	"bytes"
	"context"
	"crypto/ed25519"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	store "github.com/JBailes/aimee/server-go/modules/aimee"
	"github.com/JBailes/aimee/server-go/modules/memory"
	"github.com/RakuenSoftware/aimee-qwen/aimeeexport"
	"github.com/RakuenSoftware/aimee-qwen/memory/sparse"
	"github.com/jackc/pgx/v5"
)

type txQuery struct{ pgx.Tx }

func (q txQuery) Query(ctx context.Context, s string, a ...any) (store.Rows, error) {
	return q.Tx.Query(ctx, s, a...)
}
func (q txQuery) QueryRow(ctx context.Context, s string, a ...any) store.Row {
	return q.Tx.QueryRow(ctx, s, a...)
}
func (q txQuery) Exec(ctx context.Context, s string, a ...any) (store.Tag, error) {
	return q.Tx.Exec(ctx, s, a...)
}

func emit(out io.Writer, v any) error { return json.NewEncoder(out).Encode(v) }
func decodeFile(path string, v any) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	d := json.NewDecoder(f)
	d.DisallowUnknownFields()
	if err = d.Decode(v); err != nil {
		return err
	}
	var extra any
	if err = d.Decode(&extra); err != io.EOF {
		return errors.New("expected one JSON document")
	}
	return nil
}

func run(args []string, in io.Reader, out io.Writer) error {
	if len(args) == 0 {
		return errors.New("usage: aimee-memory-image build|import|export|compile-authorized|publish|query|read|verify|serve|serve-published|export-postgres [flags]")
	}
	cmd := args[0]
	fs := flag.NewFlagSet(cmd, flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	root := fs.String("root", "", "local image directory")
	input := fs.String("input", "", "change-set JSON")
	viewID := fs.String("view", "", "immutable view digest; defaults to CURRENT")
	expected := fs.String("expected", "", "expected CURRENT digest for compare-and-swap")
	query := fs.String("query", "", "lookup query")
	limit := fs.Int("limit", 4, "maximum returned records")
	budget := fs.Int("candidate-budget", 8192, "maximum eligible candidates; overflow fails")
	scopes := fs.String("scopes", "", "comma-separated exact scope grants; global is implicit")
	refJSON := fs.String("ref", "", "record reference JSON")
	placement := fs.String("placement", "", "server or kb for PostgreSQL export")
	scopeType := fs.String("scope-type", "", "export scope type")
	scopeValue := fs.String("scope-value", "", "export scope value")
	authorization := fs.String("authorization", "", "signed authorization from trusted Aimee control plane")
	authorityKey := fs.String("authority-key", "", "trusted Ed25519 public key file (hex)")
	subject := fs.String("subject", "", "trusted expected authorization subject")
	epoch := fs.String("policy-epoch", "", "trusted expected current authorization policy epoch")
	endpoint := fs.String("endpoint", "", "existing authenticated Aimee publication endpoint")
	ca := fs.String("ca", "", "Aimee TLS CA")
	cert := fs.String("cert", "", "Aimee client certificate")
	key := fs.String("key", "", "Aimee client private key")
	bearer := fs.String("bearer-file", "", "Aimee bearer credential file")
	streamSocket := fs.String("publication-unix", "", "existing owner-only Aimee publication socket")
	streamState := fs.String("state-root", "", "publisher-private durable resume state")
	watch := fs.Duration("watch", 0, "publisher reconciliation interval; zero runs once")
	readerGID := fs.Int("reader-gid", -1, "delivery filesystem group; defaults to existing or publisher group")
	outputRoot := fs.String("output-root", "", "new authorization-specific destination")
	internalBackup := fs.Bool("internal-backup", false, "internal unfiltered backup; never distribute to models")
	unsafeResearch := fs.Bool("unsafe-research", false, "explicitly allow an unbound research reader; never use organization data")
	namespace := fs.String("namespace", "", "authoritative source namespace")
	if err := fs.Parse(args[1:]); err != nil {
		return err
	}
	if fs.NArg() != 0 {
		return errors.New("unexpected positional arguments")
	}
	if cmd == "export-postgres" {
		if !*internalBackup {
			return errors.New("raw PostgreSQL export is control-plane only; requires --internal-backup")
		}
		role, err := memory.ParsePlacement(*placement)
		if err != nil {
			return err
		}
		dsn := os.Getenv("AIMEE_IMAGE_DATABASE_URL")
		if dsn == "" {
			return errors.New("set AIMEE_IMAGE_DATABASE_URL for read-only export")
		}
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
		defer cancel()
		conn, err := pgx.Connect(ctx, dsn)
		if err != nil {
			return errors.New("database connection failed")
		}
		defer conn.Close(ctx)
		tx, err := conn.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly})
		if err != nil {
			return errors.New("read-only snapshot failed")
		}
		defer tx.Rollback(ctx)
		records, err := aimeeexport.ExportSparseRecords(ctx, txQuery{tx}, role, memory.Scope{Type: *scopeType, Value: *scopeValue}, *namespace)
		if err != nil {
			return fmt.Errorf("export failed: %w", err)
		}
		if err = tx.Commit(ctx); err != nil {
			return errors.New("snapshot completion failed")
		}
		return emit(out, map[string]any{"records": records, "coverage": []string{"memory_rows", "row_metadata", "lifecycle", "scope", "temporal"}, "not_exported": []string{"entity_graph", "episodes", "vectors", "dedup_redirects", "policy_dependencies"}})
	}
	if *root == "" {
		return errors.New("--root is required")
	}
	if cmd == "follow-published" {
		return followPublished(*streamSocket, *endpoint, *ca, *cert, *key, *bearer, *streamState, *root, *readerGID, out)
	}
	if cmd == "fetch-published" {
		if *watch < 0 {
			return errors.New("invalid watch interval")
		}
		ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
		defer cancel()
		for {
			result, err := fetchPublication(ctx, *endpoint, *ca, *cert, *key, *bearer, *root, *readerGID)
			if err != nil {
				return err
			}
			if err = emit(out, result); err != nil {
				return err
			}
			if *watch == 0 {
				return nil
			}
			timer := time.NewTimer(*watch)
			select {
			case <-ctx.Done():
				timer.Stop()
				return nil
			case <-timer.C:
			}
		}
	}
	s := sparse.Store{Root: *root}
	if cmd == "sync-published" {
		if *outputRoot == "" || *authorization == "" || *authorityKey == "" || *subject == "" || *epoch == "" || *watch < 0 {
			return errors.New("publisher source, output, approval and trusted binding required")
		}
		raw, err := os.ReadFile(*authorityKey)
		if err != nil {
			return err
		}
		key, err := hex.DecodeString(strings.TrimSpace(string(raw)))
		if err != nil {
			return err
		}
		publisher := sparse.Publisher{Source: s, Delivery: sparse.Delivery{Root: *outputRoot}, ApprovalPath: *authorization, PublicKey: key, Subject: *subject, PolicyEpoch: *epoch, ReaderGID: *readerGID}
		ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
		defer cancel()
		for {
			result, err := publisher.Reconcile(time.Now().UTC())
			if err != nil {
				return err
			}
			if err = emit(out, result); err != nil {
				return err
			}
			if *watch == 0 {
				return nil
			}
			timer := time.NewTimer(*watch)
			select {
			case <-ctx.Done():
				timer.Stop()
				return nil
			case <-timer.C:
			}
		}
	}
	if cmd == "install-published" {
		if *outputRoot == "" {
			return errors.New("--output-root is required")
		}
		result, err := (sparse.Delivery{Root: *outputRoot}).Install(s, *expected, *readerGID)
		if err != nil {
			return err
		}
		return emit(out, result)
	}
	if cmd == "withdraw-published" {
		result, err := (sparse.Delivery{Root: *root}).Withdraw(*expected)
		if err != nil {
			return err
		}
		return emit(out, result)
	}
	if cmd == "prune-published" {
		count, err := (sparse.Delivery{Root: *root}).Prune(*expected)
		if err != nil {
			return err
		}
		return emit(out, map[string]int{"removed_snapshots": count})
	}
	if cmd == "serve-published" {
		if *authorization != "" || *authorityKey != "" || *subject != "" || *epoch != "" || *scopes != "" || *viewID != "" || *unsafeResearch {
			return errors.New("published reader accepts only the recipient image root")
		}
		return servePublished(s, in, out)
	}
	switch cmd {
	case "import":
		if !*internalBackup {
			return errors.New("raw archive import is control-plane only; requires --internal-backup")
		}
		f, err := os.Open(*input)
		if err != nil {
			return err
		}
		defer f.Close()
		id, err := s.Import(f)
		if err != nil {
			return err
		}
		return emit(out, map[string]string{"view": id})
	case "build":
		var changes sparse.ChangeSet
		if err := decodeFile(*input, &changes); err != nil {
			return err
		}
		id, err := s.Build(changes)
		if err != nil {
			return err
		}
		return emit(out, map[string]string{"view": id})
	case "publish":
		return s.Publish(*viewID, *expected)
	case "query", "read", "verify", "serve", "export", "compile-authorized":
	default:
		return errors.New("unknown command")
	}
	id := *viewID
	if id == "" {
		var err error
		id, err = s.Current()
		if err != nil {
			return err
		}
	}
	loadAuthorization := func() (sparse.SignedAuthorization, ed25519.PublicKey, error) {
		var signed sparse.SignedAuthorization
		if *authorization == "" || *authorityKey == "" || *subject == "" || *epoch == "" {
			return signed, nil, errors.New("explicit Aimee authorization binding is required")
		}
		if err := decodeFile(*authorization, &signed); err != nil {
			return signed, nil, errors.New("authorization unavailable")
		}
		b, err := os.ReadFile(*authorityKey)
		if err != nil {
			return signed, nil, errors.New("authority key unavailable")
		}
		key, err := hex.DecodeString(strings.TrimSpace(string(b)))
		if err != nil {
			return signed, nil, errors.New("invalid authority key")
		}
		_, err = sparse.VerifyAuthorization(signed, key, *subject, *epoch, time.Now())
		return signed, key, err
	}
	if cmd == "compile-authorized" {
		signed, key, err := loadAuthorization()
		if err != nil {
			return err
		}
		result, err := s.CompileAuthorized(sparse.Store{Root: *outputRoot}, signed, key, *subject, *epoch, time.Now())
		if err != nil {
			return err
		}
		return emit(out, map[string]string{"view": result, "authorization": signed.Digest()})
	}
	if cmd == "export" && *internalBackup {
		if *scopes != "" || *authorization != "" {
			return errors.New("internal backup is unfiltered; scope/authorization flags would be misleading")
		}
		return s.Export(id, out)
	}
	v, err := s.Open(id)
	if err != nil {
		return err
	}
	defer func() { v.Close() }()
	grants := map[string]bool{}
	for _, g := range strings.Split(*scopes, ",") {
		if g != "" {
			grants[g] = true
		}
	}
	var bound sparse.SignedAuthorization
	var boundKey ed25519.PublicKey
	if cmd == "serve" && !*unsafeResearch || cmd == "export" || *authorization != "" {
		bound, boundKey, err = loadAuthorization()
		if err != nil {
			return err
		}
		if err = v.CheckAuthorization(bound, boundKey, *subject, *epoch, time.Now()); err != nil {
			return err
		}
		var grant sparse.Authorization
		_ = json.Unmarshal(bound.Grant, &grant)
		if *scopes != "" {
			return errors.New("authorized reader scopes come only from Aimee's grant")
		}
		grants = map[string]bool{}
		for _, g := range grant.Grants {
			grants[g] = true
		}
	}
	if cmd == "export" {
		return s.Export(id, out)
	}
	switch cmd {
	case "verify":
		if err = v.Verify(); err != nil {
			return err
		}
		return emit(out, map[string]any{"view": id, "verified": true, "layers": v.Layers})
	case "read":
		var ref sparse.Ref
		if err = json.Unmarshal([]byte(*refJSON), &ref); err != nil {
			return err
		}
		r, err := v.Get(ref, grants, time.Now())
		if err != nil {
			return err
		}
		return emit(out, r)
	case "query":
		r, err := v.Search(*query, *limit, *budget, grants, time.Now())
		if err != nil {
			return err
		}
		return emit(out, r)
	}
	var referenceLookup *sparse.ReferenceLookup
	if len(boundKey) > 0 {
		var grant sparse.Authorization
		_ = json.Unmarshal(bound.Grant, &grant)
		referenceLookup, err = sparse.NewReferenceLookup(v, grant)
		if err != nil {
			return err
		}
	}
	// Persistent local transport: indexes stay in RAM across requests. pin is
	// explicit so a publication never swaps generations in mid-generation.
	scan := bufio.NewScanner(in)
	scan.Buffer(make([]byte, 4096), 1<<20)
	for scan.Scan() {
		var req struct {
			Op        string          `json:"op"`
			Authority string          `json:"authority"`
			Query     string          `json:"query"`
			Limit     int             `json:"limit"`
			Response  json.RawMessage `json:"response"`
		}
		if err = json.Unmarshal(scan.Bytes(), &req); err != nil {
			if err = emit(out, map[string]string{"error": "invalid request"}); err != nil {
				return err
			}
			continue
		}
		var response any
		// Check expiry/revocation before every read, including an already-pinned view.
		if len(boundKey) > 0 {
			current, key, e := loadAuthorization()
			if e != nil || current.Digest() != bound.Digest() || !bytes.Equal(key, boundKey) {
				if e = emit(out, map[string]string{"error": "authorization changed or unavailable"}); e != nil {
					return e
				}
				continue
			}
		}
		if req.Op == "pin" {
			newID := *viewID
			if newID == "" {
				newID, err = s.Current()
			}
			if err == nil && newID != v.ID {
				var next *sparse.View
				next, err = s.Open(newID)
				if err == nil && len(boundKey) > 0 {
					err = next.CheckAuthorization(bound, boundKey, *subject, *epoch, time.Now())
					if err != nil {
						next.Close()
					}
				}
				if err == nil {
					v.Close()
					v = next
					if referenceLookup != nil {
						var grant sparse.Authorization
						_ = json.Unmarshal(bound.Grant, &grant)
						referenceLookup, err = sparse.NewReferenceLookup(v, grant)
					}
				}
			}
			if err == nil {
				response = map[string]string{"view": v.ID, "authorization": bound.Digest()}
			}
		} else if req.Op == "search_restriction" && len(boundKey) > 0 {
			var grant sparse.Authorization
			_ = json.Unmarshal(bound.Grant, &grant)
			response, err = sparse.RestrictSearch(grant, req.Authority)
		} else if req.Op == "authorize_response" && len(boundKey) > 0 {
			var grant sparse.Authorization
			_ = json.Unmarshal(bound.Grant, &grant)
			err = v.AuthorizeResponse(req.Response, grant, time.Now())
			if err == nil {
				response = map[string]string{"authorized": bound.Digest()}
			}
		} else if req.Op == "resolve_response" && len(boundKey) > 0 {
			var grant sparse.Authorization
			_ = json.Unmarshal(bound.Grant, &grant)
			var refs []sparse.Ref
			refs, err = v.ResolveResponse(req.Response, grant, time.Now())
			if err == nil {
				response = map[string]any{"refs": refs, "authorization": bound.Digest(), "view": v.ID}
			}
		} else if req.Op == "recall" {
			recalled := v.Recall(req.Query, req.Limit, req.Authority, grants, time.Now())
			if recalled.Outcome == "uncovered" && referenceLookup != nil {
				recalled = referenceLookup.Recall(req.Query, req.Limit, req.Authority, time.Now())
			}
			response = recalled
		} else if req.Op == "search" {
			response, err = v.Search(req.Query, req.Limit, *budget, grants, time.Now())
		} else {
			err = errors.New("unsupported operation")
		}
		if err != nil {
			response = map[string]string{"error": err.Error()}
			err = nil
		}
		if err = emit(out, response); err != nil {
			return err
		}
	}
	return scan.Err()
}
func main() {
	if err := run(os.Args[1:], os.Stdin, os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
