// Exhaustive local lookup verification. Not part of model serving.
package main

import (
	"crypto/ed25519"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"github.com/JBailes/aimee/server-go/modules/memory/sparse"
	"os"
	"sort"
	"strings"
	"time"
)

func main() {
	root := flag.String("root", "", "authorized image")
	source := flag.String("records", "knowledge/general-v1/records.json", "canonical test expectations")
	grant := flag.String("authorization", "", "grant")
	public := flag.String("public-key", "", "public key")
	flag.Parse()
	must := func(e error) {
		if e != nil {
			panic(e)
		}
	}
	raw, e := os.ReadFile(*source)
	must(e)
	var c sparse.ChangeSet
	must(json.Unmarshal(raw, &c))
	raw, e = os.ReadFile(*grant)
	must(e)
	var signed sparse.SignedAuthorization
	must(json.Unmarshal(raw, &signed))
	pub, e := os.ReadFile(*public)
	must(e)
	key, e := hex.DecodeString(strings.TrimSpace(string(pub)))
	must(e)
	a, e := sparse.VerifyAuthorization(signed, ed25519.PublicKey(key), "general-kb-research", "research-1", time.Now())
	must(e)
	store := sparse.Store{Root: *root}
	id, e := store.Current()
	must(e)
	v, e := store.Open(id)
	must(e)
	defer v.Close()
	must(v.CheckAuthorization(signed, key, a.Subject, a.PolicyEpoch, time.Now()))
	lookup, e := sparse.NewReferenceLookup(v, a)
	must(e)
	failures := []map[string]any{}
	times := []float64{}
	for _, r := range c.Records {
		start := time.Now()
		result := lookup.Recall("Please provide the reference entry for "+r.Key+".", 4, "research-aimee-103", time.Now())
		times = append(times, float64(time.Since(start).Nanoseconds())/1e6)
		var answer struct {
			Facts []struct {
				ID      string
				Content string
			}
		}
		must(json.Unmarshal(resultOrEmpty(result.Response), &answer))
		if result.Outcome != "hit" || len(answer.Facts) != 1 || answer.Facts[0].ID != r.ID || answer.Facts[0].Content != r.Content {
			failures = append(failures, map[string]any{"id": r.ID, "outcome": result.Outcome, "returned": answer.Facts})
		}
	}
	sort.Float64s(times)
	sum := 0.0
	for _, x := range times {
		sum += x
	}
	out := map[string]any{"records": len(c.Records), "passed": len(c.Records) - len(failures), "failures": failures, "warm_lookup_ms": map[string]float64{"median": times[len(times)/2], "p95": times[int(.95*float64(len(times)))], "mean": sum / float64(len(times))}, "scope": "warm core read, startup authorization checked once; excludes per-message lease verification"}
	b, _ := json.MarshalIndent(out, "", "  ")
	fmt.Println(string(b))
}
func resultOrEmpty(b []byte) []byte {
	if len(b) == 0 {
		return []byte(`{"facts":[]}`)
	}
	return b
}
