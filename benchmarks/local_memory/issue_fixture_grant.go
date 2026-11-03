// Research fixture issuer ONLY. This does not evaluate Aimee authorization.
// Production must obtain approvals from Aimee's authenticated policy owner.
// Never install this tool or its private key in the model's filesystem.
package main

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"github.com/RakuenSoftware/aimee-native/memory/sparse"
	"os"
)

func main() {
	input := flag.String("input", "", "explicit research approval plan")
	output := flag.String("output", "", "signed decision")
	keyFile := flag.String("key", "", "fixture-only private key")
	publicFile := flag.String("public-key", "", "fixture public key")
	flag.Parse()
	must := func(e error) {
		if e != nil {
			fmt.Fprintln(os.Stderr, e)
			os.Exit(1)
		}
	}
	var plan struct {
		Authorization sparse.Authorization  `json:"authorization"`
		Records       []sparse.Record       `json:"records"`
		Reads         []sparse.ReadContract `json:"reads"`
	}
	raw, e := os.ReadFile(*input)
	must(e)
	must(json.Unmarshal(raw, &plan))
	private, e := os.ReadFile(*keyFile)
	if os.IsNotExist(e) {
		_, key, err := ed25519.GenerateKey(rand.Reader)
		must(err)
		private = key
		must(os.WriteFile(*keyFile, key, 0600))
	} else {
		must(e)
	}
	if len(private) != ed25519.PrivateKeySize {
		must(fmt.Errorf("invalid fixture key"))
	}
	for _, r := range plan.Records {
		plan.Authorization.Records = append(plan.Authorization.Records, sparse.AuthorizeRecord(r))
	}
	for _, r := range plan.Reads {
		plan.Authorization.ReadDigests = append(plan.Authorization.ReadDigests, sparse.ReadDigest(r))
	}
	signed, e := sparse.SignAuthorization(plan.Authorization, private)
	must(e)
	raw, e = json.Marshal(signed)
	must(e)
	must(os.WriteFile(*output, raw, 0600))
	pub := ed25519.PrivateKey(private).Public().(ed25519.PublicKey)
	must(os.WriteFile(*publicFile, []byte(hex.EncodeToString(pub)), 0600))
	fmt.Println(signed.Digest())
}
