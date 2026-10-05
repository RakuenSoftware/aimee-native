// Public synthetic archive and published-reader scaling probe. Signing keys live
// only in process memory. This is not a production authorization policy probe.
package main

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"flag"
	"fmt"
	sparse "github.com/RakuenSoftware/aimee-qwen/memory/sparse"
	"os"
	"path/filepath"
	"sort"
	"time"
)

func must(e error) {
	if e != nil {
		panic(e)
	}
}
func main() {
	root := flag.String("root", "", "exclusive output directory")
	count := flag.Int("distractors", 1000, "unrelated physically published records")
	routing := flag.Bool("routing", true, "publisher-approved bundles")
	grounded := flag.Bool("grounded-holdout", false, "fresh frozen facts with explicit authoritative alias identities")
	holdout := flag.Bool("holdout", false, "frozen fresh public facts for hybrid-state holdout")
	framing := flag.Bool("framing-suite", false, "original regressions plus implicit-alias and fresh frozen framing facts")
	routeDistractors := flag.Bool("route-distractors", false, "grow the route catalog as well as the archive")
	flag.Parse()
	if *root == "" || *count < 0 || (*framing && (*holdout || *grounded)) || (*holdout && *grounded) {
		panic("invalid arguments")
	}
	must(os.Mkdir(*root, 0700))
	start := time.Now()
	now := time.Now()
	src := sparse.Store{Root: filepath.Join(*root, "source")}
	dst := sparse.Store{Root: filepath.Join(*root, "published")}
	names := []string{"orinth", "velmar", "selvek", "neris", "tavren", "merisol"}
	contents := []string{"Orinth station access code is 7391.", "Velmar station access code is 4826.", "Selvek station access code is 9153.", "Neris relay connects to Orinth station.", "Tavren relay connects to Velmar station.", "Merisol relay connects to Selvek station."}
	if *holdout {
		names = []string{"aldren", "voskar", "tinrel", "dalven", "osreth", "karvin"}
		contents = []string{"Aldren station access code is 2648.", "Voskar station access code is 5802.", "Tinrel station access code is 6739.", "Dalven relay connects to Aldren station.", "Osreth relay connects to Voskar station.", "Karvin relay connects to Tinrel station."}
	}
	if *grounded {
		names = []string{"larneth", "quorin", "espira", "renvik", "parsol", "vireth", "identity-renvik", "identity-parsol", "identity-vireth"}
		contents = []string{"Larneth station access code is 3179.", "Quorin station access code is 8046.", "Espira station access code is 6528.", "Renvik relay connects to Larneth station.", "Parsol relay connects to Quorin station.", "Vireth relay connects to Espira station.", "Renvik outpost is another name for Renvik relay.", "Parsol outpost is another name for Parsol relay.", "Vireth outpost is another name for Vireth relay."}
	}
	if *framing {
		names = append(names, "aldren", "voskar", "tinrel", "dalven", "osreth", "karvin", "dreskal", "ulneth", "pavrin", "mevris", "talvek", "jorrel")
		contents = append(contents, "Aldren station access code is 2648.", "Voskar station access code is 5802.", "Tinrel station access code is 6739.", "Dalven relay connects to Aldren station.", "Osreth relay connects to Voskar station.", "Karvin relay connects to Tinrel station.", "Dreskal station access code is 8621.", "Ulneth station access code is 3497.", "Pavrin station access code is 7054.", "Mevris relay connects to Dreskal station.", "Talvek relay connects to Ulneth station.", "Jorrel relay connects to Pavrin station.")
	}
	records := make([]sparse.Record, 0, *count+len(names))
	for i := 0; i < *count+len(names); i++ {
		name := fmt.Sprintf("distractor%d", i-len(names))
		content := fmt.Sprintf("Unrelated synthetic record %d has value %d.", i, i+10000)
		key := fmt.Sprintf("unrelated item%d", i)
		if i < len(names) {
			name = names[i]
			content = contents[i]
			key = name + " station"
			if i >= 3 && (!*framing || i%6 >= 3) {
				key = name + " relay"
			}
		}
		records = append(records, sparse.Record{Ref: sparse.Ref{Namespace: "public-research-fixture", ID: name, Revision: "1"}, Scope: sparse.Scope{Type: "global", Value: "_global"}, Key: key, Content: content, Kind: "fact", Tier: "L3", Confidence: 1, Lifecycle: "active"})
	}
	id, e := src.Build(sparse.ChangeSet{Namespace: "public-research-fixture", Kind: "general", Generation: 1, Source: "public synthetic research fixture", Coverage: []string{"synthetic"}, Records: records})
	must(e)
	pub, key, e := ed25519.GenerateKey(rand.Reader)
	must(e)
	auth := sparse.Authorization{Version: 1, ID: "synthetic-release", Subject: "research", PolicyEpoch: "fixture-1", SourceView: id, Active: true, ValidUntil: now.Add(24 * time.Hour).Format(time.RFC3339), ReferenceLookups: []sparse.ReferenceLookupPolicy{{Namespace: "public-research-fixture", Authority: "public-research", Mode: "exact-key-v1"}}}
	for _, r := range records {
		auth.Records = append(auth.Records, sparse.AuthorizeRecord(r))
	}
	if *routing {
		routeNames := names[:6]
		if *framing {
			routeNames = names
		}
		if *routeDistractors {
			routeNames = make([]string, len(records))
			for i, r := range records {
				routeNames[i] = r.ID
			}
		}
		for i, name := range routeNames {
			refs := []sparse.Ref{records[i].Ref}
			if (i >= 3 && i < 6) || (*framing && i%6 >= 3) {
				refs = append(refs, records[i-3].Ref)
				if *grounded {
					refs = append(refs, records[i+3].Ref)
				}
			}
			auth.CandidateRoutes = append(auth.CandidateRoutes, sparse.CandidateRoute{Partition: name, Authority: "public-research", Cues: []string{name, name + " outpost"}, Records: refs})
		}
	}
	signed, e := sparse.SignAuthorization(auth, key)
	must(e)
	published, e := src.CompileAuthorized(dst, signed, pub, auth.Subject, auth.PolicyEpoch, now)
	must(e)
	buildMS := float64(time.Since(start).Microseconds()) / 1000
	start = time.Now()
	p, e := dst.OpenPublished(published)
	must(e)
	defer p.Close()
	openMS := float64(time.Since(start).Microseconds()) / 1000
	address := sparse.NativeAddress{Schema: 1, View: p.View.ID, Representation: "text-query-v1"}
	start = time.Now()
	cold, e := p.RouteNative(address, "What access code belongs to "+names[3]+" relay's station?", 6, "public-research", now)
	must(e)
	coldUS := time.Since(start).Microseconds()
	timings := make([]int64, 1000)
	for i := range timings {
		start = time.Now()
		r, e := p.RouteNative(address, "What access code belongs to "+names[3]+" relay's station?", 6, "public-research", now)
		must(e)
		if *routing && (r.Outcome != "hit" || r.CandidateRecords != map[bool]int{false: 2, true: 3}[*grounded]) {
			panic("bundle coverage changed")
		}
		timings[i] = time.Since(start).Nanoseconds()
	}
	sort.Slice(timings, func(i, j int) bool { return timings[i] < timings[j] })
	report := map[string]any{"archive_records": len(records), "route_partitions": len(auth.CandidateRoutes), "build_ms": buildMS, "open_ms": openMS, "cold_route_us": coldUS, "cold_outcome": cold.Outcome, "warm_route_median_ns": timings[500], "warm_route_p95_ns": timings[950], "warm_samples": len(timings), "candidate_records": cold.CandidateRecords, "candidate_partitions": cold.CandidatePartitions, "view": published, "scope": "owner-approved exact cues; physically published archive; warm host-wall includes canonical source resolution; startup and fallback are not constant"}
	data, e := json.MarshalIndent(report, "", "  ")
	must(e)
	must(os.WriteFile(filepath.Join(*root, "scaling.json"), append(data, '\n'), 0600))
	fmt.Println(string(data))
}
