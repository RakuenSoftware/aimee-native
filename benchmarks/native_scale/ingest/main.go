// Research driver around the actual Aimee extractor, memory store and exporter.
package main
import("bufio";"context";"encoding/json";"fmt";"os";"strings";"github.com/jackc/pgx/v5"; store "github.com/JBailes/aimee/server-go/modules/aimee"; "github.com/JBailes/aimee/server-go/modules/memory"; "github.com/RakuenSoftware/aimee-qwen/aimeeexport")
type DB struct{c *pgx.Conn}
func(d DB)Exec(c context.Context,q string,a ...any)(store.Tag,error){return d.c.Exec(c,q,a...)}
func(d DB)Query(c context.Context,q string,a ...any)(store.Rows,error){return d.c.Query(c,q,a...)}
func(d DB)QueryRow(c context.Context,q string,a ...any)store.Row{return d.c.QueryRow(c,q,a...)}
func must(e error){if e!=nil{panic(e)}}
func main(){ctx:=context.Background();conn,e:=pgx.Connect(ctx,"postgres:///aimee_scale_20260922?host=/var/run/postgresql");must(e);defer conn.Close(ctx);db:=DB{conn};_,e=db.Exec(ctx,`CREATE TABLE IF NOT EXISTS user_memories(id bigserial primary key,kind text NOT NULL,tier text NOT NULL,key text NOT NULL,content text NOT NULL,confidence double precision NOT NULL,lifecycle_state text NOT NULL DEFAULT 'active',valid_from timestamptz,valid_until timestamptz,activation_suppressed integer NOT NULL DEFAULT 0,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(kind,key))`);must(e)
 data,e:=memory.NewPostgresDataStore(db,memory.PlacementServer);must(e);scope:=memory.Scope{Type:"user",Value:"_user"};scanner:=bufio.NewScanner(os.Stdin);out:=json.NewEncoder(os.Stdout)
 for scanner.Scan(){var row struct{Key string `json:"key"`;Text string `json:"text"`};must(json.Unmarshal(scanner.Bytes(),&row));triples:=memory.ExtractPatterns(row.Text,4);if len(triples)!=1{panic("expected one extracted personal assertion")};t:=triples[0];if !strings.HasPrefix(row.Text,"My "){panic("explicit assertion required")};verdict:=memory.GateCheck(t.SubjectKind,t.RelType,t.ObjectKind);if verdict!=memory.FactAccept && verdict!=memory.FactNovel{panic("candidate rejected by ontology gate")}
 r,e:=data.Put(ctx,scope,memory.Record{Kind:"fact",Tier:"L3",Key:row.Key,Content:fmt.Sprintf("The user's %s is %s.",row.Key,t.Object),Confidence:1});must(e);must(out.Encode(map[string]any{"input":row,"triples":triples,"gate_verdict":verdict,"stored":r}))
 };must(scanner.Err());tx,e:=conn.BeginTx(ctx,pgx.TxOptions{IsoLevel:pgx.RepeatableRead,AccessMode:pgx.ReadOnly});must(e);defer tx.Rollback(ctx)
 // The export must use the same read-only transaction for all source rows.
 records,e:=aimeeexport.ExportSparseRecords(ctx,TX{tx},memory.PlacementServer,scope,"scale-personal");must(e);must(tx.Commit(ctx));f,e:=os.OpenFile(os.Args[1],os.O_WRONLY|os.O_CREATE|os.O_EXCL,0600);must(e);defer f.Close();must(json.NewEncoder(f).Encode(records))
}
type TX struct{t pgx.Tx}
func(d TX)Exec(c context.Context,q string,a ...any)(store.Tag,error){return d.t.Exec(c,q,a...)}
func(d TX)Query(c context.Context,q string,a ...any)(store.Rows,error){return d.t.Query(c,q,a...)}
func(d TX)QueryRow(c context.Context,q string,a ...any)store.Row{return d.t.QueryRow(c,q,a...)}
