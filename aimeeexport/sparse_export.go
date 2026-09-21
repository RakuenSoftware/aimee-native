package aimeeexport

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	store "github.com/JBailes/aimee/server-go/modules/aimee"
	"github.com/JBailes/aimee/server-go/modules/memory"
	"github.com/RakuenSoftware/aimee-qwen/memory/sparse"
)

// ExportSparseRecords is a control-plane source export, not an authorization
// decision. Scope normalization selects storage; it does not prove caller access.
// Never distribute this raw output to a model. CompileAuthorized must apply an
// independently issued, exact-object release before distribution. The caller
// supplies a read-only repeatable-read transaction. This initial exporter covers
// memory rows, not the entire KB ontology/episode/vector corpus; coverage must
// be declared in the image manifest. Original row fields remain in Metadata.
func ExportSparseRecords(ctx context.Context, db store.Queryer, placement memory.Placement, scope memory.Scope, namespace string) ([]sparse.Record, error) {
	rows, e := memory.ExportMemoryRows(ctx, db, placement, scope)
	return projectRows(rows, namespace, e)
}
func ExportSparseRecordsSelected(ctx context.Context, db store.Queryer, placement memory.Placement, scope memory.Scope, namespace string, ids []string) ([]sparse.Record, error) {
	rows, e := memory.ExportMemoryRowsSelected(ctx, db, placement, scope, ids)
	return projectRows(rows, namespace, e)
}
func projectRows(source *memory.MemoryExport, namespace string, err error) ([]sparse.Record, error) {
	if err != nil {
		return nil, err
	}
	result := []sparse.Record{}
	for _, raw := range source.Rows {
		r, e := SparseRecordFromRow(raw, source.Scope, namespace)
		if e != nil {
			return nil, e
		}
		result = append(result, r)
	}
	return result, nil
}

// SparseRecordFromRow preserves source metadata and hashes the canonical row as
// its revision. It accepts the normalized scope from the owning memory module.
func SparseRecordFromRow(raw []byte, scope memory.Scope, namespace string) (sparse.Record, error) {
	var row map[string]json.RawMessage
	if err := json.Unmarshal(raw, &row); err != nil {
		return sparse.Record{}, err
	}
	canonical, err := json.Marshal(row)
	if err != nil {
		return sparse.Record{}, err
	}
	sum := sha256.Sum256(canonical)
	str := func(key string) string { var value string; _ = json.Unmarshal(row[key], &value); return value }
	var id int64
	if err = json.Unmarshal(row["id"], &id); err != nil || id <= 0 {
		return sparse.Record{}, fmt.Errorf("memory export requires positive source id")
	}
	var confidence float64
	if err = json.Unmarshal(row["confidence"], &confidence); err != nil {
		return sparse.Record{}, fmt.Errorf("memory export requires confidence")
	}
	r := sparse.Record{Ref: sparse.Ref{Namespace: namespace, ID: strconv.FormatInt(id, 10), Revision: hex.EncodeToString(sum[:])}, Scope: sparse.Scope{Type: scope.Type, Value: scope.Value}, Key: str("key"), Content: str("content"), Kind: str("kind"), Tier: str("tier"), Confidence: confidence, Lifecycle: str("lifecycle_state"), Metadata: canonical}
	var suppressed int
	_ = json.Unmarshal(row["activation_suppressed"], &suppressed)
	r.Suppressed = suppressed != 0
	for field, dst := range map[string]*string{"valid_from": &r.ValidFrom, "valid_until": &r.ValidUntil} {
		if value := strings.TrimSpace(str(field)); value != "" {
			t, err := memory.ParseMemoryTimestamp(value)
			if err != nil {
				return r, err
			}
			*dst = t.UTC().Format(time.RFC3339Nano)
		}
	}
	return r, nil
}
