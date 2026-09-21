package sparse

import (
	"path/filepath"
	"testing"
)

func TestApprovedCuesAndCollisionAbstention(t *testing.T) {
	src, _, rs, a, pub, priv := authorizationFixture(t)
	a.ReferenceCues = []ReferenceCue{{rs[0].Ref, "alternate astronomy name", "test"}, {rs[1].Ref, "alternate project name", "test"}, {rs[0].Ref, "shared alias name", "test"}, {rs[1].Ref, "shared alias name", "test"}, {rs[0].Ref, "alternate astronomy name", "test"}}
	dst := Store{filepath.Join(t.TempDir(), "published")}
	id, e := src.CompileAuthorized(dst, signedGrant(t, a, priv), pub, a.Subject, a.PolicyEpoch, testNow)
	if e != nil {
		t.Fatal(e)
	}
	p, e := dst.OpenPublished(id)
	if e != nil {
		t.Fatal(e)
	}
	defer p.Close()
	for _, tc := range []struct{ q, outcome string }{{"What about alternate astronomy name?", "hit"}, {"alternate project name", "hit"}, {"alternate project name and alternate astronomy name", "hit"}, {"shared alias name", "ambiguous"}, {"CANARY_PRIVATE_ALIAS", "uncovered"}} {
		r, e := p.Recall(tc.q, 4, "test", testNow)
		if e != nil || r.Outcome != tc.outcome {
			t.Fatalf("%s: %+v %v", tc.q, r, e)
		}
	}
	a.ReferenceCues = append(a.ReferenceCues, ReferenceCue{rs[2].Ref, "forbidden record alias", "test"})
	if _, e = src.CompileAuthorized(Store{filepath.Join(t.TempDir(), "bad")}, signedGrant(t, a, priv), pub, a.Subject, a.PolicyEpoch, testNow); e == nil {
		t.Fatal("unapproved cue source exported")
	}
}
