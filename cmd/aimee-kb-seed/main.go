// Offline source preparation. This tool holds no model or authorization keys.
// It delegates image compilation to Aimee's existing model-independent package.
package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"github.com/RakuenSoftware/aimee-qwen/memory/sparse"
	"io"
	"os"
)

func build(root, input string) (string, error) {
	raw, err := os.ReadFile(input)
	if err != nil {
		return "", err
	}
	var c sparse.ChangeSet
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.DisallowUnknownFields()
	if err = dec.Decode(&c); err != nil {
		return "", err
	}
	var extra any
	if dec.Decode(&extra) != io.EOF {
		return "", fmt.Errorf("trailing input")
	}
	if c.Kind != "general" || c.Upstream != "" || c.Authorization != "" || len(c.Records) == 0 {
		return "", fmt.Errorf("standalone general source required")
	}
	for _, r := range c.Records {
		var m struct {
			Provenance struct {
				URL     string `json:"source_url"`
				Checked string `json:"checked_on"`
			} `json:"provenance"`
			Semantic map[string]any `json:"semantic"`
		}
		if json.Unmarshal(r.Metadata, &m) != nil || m.Provenance.URL == "" || m.Provenance.Checked == "" || len(m.Semantic) == 0 {
			return "", fmt.Errorf("canonical semantics and provenance required for %s", r.ID)
		}
	}
	return (sparse.Store{Root: root}).Build(c)
}
func main() {
	root := flag.String("root", "", "control-plane source store (not a model image)")
	input := flag.String("input", "knowledge/general-v0/records.json", "reviewed general source change set")
	flag.Parse()
	if *root == "" {
		fmt.Fprintln(os.Stderr, "--root required")
		os.Exit(1)
	}
	id, err := build(*root, *input)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	_ = json.NewEncoder(os.Stdout).Encode(map[string]any{"view": id, "published": false, "authorized_for_model": false})
}
