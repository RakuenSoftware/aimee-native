package aimeeexport

import (
	"context"
	"encoding/json"
	"reflect"
	"strings"
	"testing"

	store "github.com/JBailes/aimee/server-go/modules/aimee"
	"github.com/JBailes/aimee/server-go/modules/memory"
)

type sparseExportRows struct {
	done bool
	raw  []byte
}

func (r *sparseExportRows) Next() bool {
	if r.done {
		return false
	}
	r.done = true
	return true
}
func (r *sparseExportRows) Scan(dst ...any) error { *dst[0].(*[]byte) = r.raw; return nil }
func (r *sparseExportRows) Err() error            { return nil }
func (r *sparseExportRows) Close()                {}

type sparseExportDB struct {
	sql  string
	args []any
	raw  []byte
}

func (q *sparseExportDB) Query(_ context.Context, sql string, args ...any) (store.Rows, error) {
	q.sql = sql
	q.args = args
	return &sparseExportRows{raw: q.raw}, nil
}
func (q *sparseExportDB) QueryRow(context.Context, string, ...any) store.Row {
	panic("unexpected QueryRow")
}
func (q *sparseExportDB) Exec(context.Context, string, ...any) (store.Tag, error) {
	panic("export attempted write")
}

func TestSparseExporterReusesPlacementScopeAndPreservesMetadata(t *testing.T) {
	raw := []byte(`{"id":5,"key":"drink","content":"oolong","kind":"fact","tier":"L3","confidence":1,"lifecycle_state":"active","source_session":"s1","valid_until":"2027-01-01T00:00:00Z","activation_suppressed":1}`)
	db := &sparseExportDB{raw: raw}
	rows, err := ExportSparseRecords(context.Background(), db, memory.PlacementServer, memory.Scope{}, "personal")
	if err != nil || len(rows) != 1 {
		t.Fatalf("export: %v %v", rows, err)
	}
	if !strings.Contains(db.sql, "FROM user_memories") || len(db.args) != 0 {
		t.Fatal("server accessed KB")
	}
	if rows[0].Scope.Type != "user" || !rows[0].Suppressed || rows[0].ValidUntil != "2027-01-01T00:00:00Z" {
		t.Fatalf("lost policy: %+v", rows[0])
	}
	var metadata map[string]any
	if err = json.Unmarshal(rows[0].Metadata, &metadata); err != nil || metadata["source_session"] != "s1" {
		t.Fatal("lost source metadata")
	}
	before := db.sql
	if _, err := ExportSparseRecords(context.Background(), db, memory.PlacementServer, memory.Scope{Type: "global"}, "personal"); err == nil || db.sql != before {
		t.Fatal("wrong-scope export reached DB")
	}
	_, err = ExportSparseRecords(context.Background(), db, memory.PlacementKB, memory.Scope{Type: "project", Value: "p"}, "project-kb")
	if err != nil || !strings.Contains(db.sql, "FROM memories") || !reflect.DeepEqual(db.args, []any{"project", "p"}) {
		t.Fatalf("KB scope: %v %v", db.args, err)
	}
	if _, err := ExportSparseRecords(context.Background(), db, memory.PlacementKB, memory.Scope{Type: "user"}, "kb"); err == nil {
		t.Fatal("KB exported user scope")
	}
}

func TestSelectedExportNeverFallsBackToWholeStore(t *testing.T) {
	db := &sparseExportDB{raw: []byte(`{"id":5,"key":"drink","content":"oolong","kind":"fact","tier":"L3","confidence":1,"lifecycle_state":"active"}`)}
	for _, ids := range [][]string{nil, {}} {
		rows, e := ExportSparseRecordsSelected(context.Background(), db, memory.PlacementServer, memory.Scope{}, "personal", ids)
		if e != nil || len(rows) != 0 || db.sql != "" {
			t.Fatal("empty selection queried source", e)
		}
	}
	if _, e := ExportSparseRecordsSelected(context.Background(), db, memory.PlacementServer, memory.Scope{}, "personal", []string{"5 OR 1=1"}); e == nil || db.sql != "" {
		t.Fatal("invalid ID reached source")
	}
	// The core exports raw rows, including lifecycle metadata. Selection must
	// remain parameterized; publication applies eligibility and release policy.
	rows, e := ExportSparseRecordsSelected(context.Background(), db, memory.PlacementServer, memory.Scope{}, "personal", []string{"5"})
	if e != nil || len(rows) != 1 || !strings.Contains(db.sql, "id IN (SELECT jsonb_array_elements_text($1::jsonb)::bigint)") || !reflect.DeepEqual(db.args, []any{`["5"]`}) {
		t.Fatalf("not parameterized: %s %+v %v", db.sql, db.args, e)
	}
}
