package sparse

import (
	"encoding/json"
	"testing"
)

func TestRestrictedResponseAndAbstention(t *testing.T) {
	src, head, rs, a, _, _ := authorizationFixture(t)
	v := open(t, src, head)
	r, err := RestrictSearch(a, "kb")
	if err != nil || len(r.IDs) != 1 || r.IDs[0] != 1 {
		t.Fatalf("%+v %v", r, err)
	}
	body := map[string]any{"status": "ok", "facts": []any{}, "windows": []any{}, "active_context_missing": false, "restriction": r}
	check := func(want bool) {
		t.Helper()
		b, _ := json.Marshal(body)
		_, e := v.ResolveResponse(b, a, testNow)
		if (e == nil) != want {
			t.Fatalf("response accepted=%v want=%v: %v", e == nil, want, e)
		}
	}
	check(true)
	body["facts"] = nil
	check(false)
	body["facts"] = []any{}
	delete(body, "restriction")
	check(false)
	body["restriction"] = r
	bad := r
	bad.IDs = []int64{1, 2}
	body["restriction"] = bad
	check(false)
	bad = r
	bad.Authorization = "bad"
	body["restriction"] = bad
	check(false)
	body["restriction"] = r
	body["facts"] = []any{map[string]any{"id": "1", "content": rs[1].Content}}
	check(true)
	body["facts"] = []any{map[string]any{"id": "1", "content": rs[0].Content}}
	check(false) // same ID, wrong namespace
	body["facts"] = []any{map[string]any{"id": "1", "content": "changed"}}
	check(false)
	empty, err := RestrictSearch(a, "unknown")
	if err != nil || len(empty.IDs) != 0 || empty.IDs == nil {
		t.Fatal("empty namespace widened")
	}
}
