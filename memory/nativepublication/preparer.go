package nativepublication

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"os/exec"
	"reflect"
	"syscall"
	"time"
)

// Preparer is private hosted glue for the existing Rust preparation boundary.
// Template and binary paths are operator-owned, never accepted over HTTP.
// The caller MUST first resolve identity and authorize the recipient/source via
// Aimee. This type neither creates grants nor substitutes for that resolver.
type Preparer struct {
	Binary, Template string
	Profile          Profile
}
type limitedOutput struct {
	bytes.Buffer
	limit int
}

func (b *limitedOutput) Write(p []byte) (int, error) {
	if len(p) > b.limit-b.Len() {
		return 0, errors.New("preparation response too large")
	}
	return b.Buffer.Write(p)
}
func (p Preparer) execute(ctx context.Context, recipient, query string, check bool) (Prepared, error) {
	raw, e := os.ReadFile(p.Template)
	if e != nil {
		return Prepared{}, e
	}
	var c map[string]json.RawMessage
	if e = json.Unmarshal(raw, &c); e != nil {
		return Prepared{}, e
	}
	var configured string
	if json.Unmarshal(c["recipient"], &configured) != nil || configured != recipient {
		return Prepared{}, denied
	}
	if p.Profile.Recipient != recipient || p.Profile.Schema != 1 {
		return Prepared{}, denied
	}
	var model string
	if json.Unmarshal(c["model_revision"], &model) != nil || model != p.Profile.Model {
		return Prepared{}, denied
	}
	c["query"], _ = json.Marshal(query)
	f, e := os.CreateTemp("", "aimee-native-request-*.json")
	if e != nil {
		return Prepared{}, e
	}
	defer os.Remove(f.Name())
	encoded, e := json.Marshal(c)
	if e != nil {
		f.Close()
		return Prepared{}, e
	}
	if _, e = f.Write(encoded); e != nil {
		f.Close()
		return Prepared{}, e
	}
	if e = f.Close(); e != nil {
		return Prepared{}, e
	}
	ctx, cancel := context.WithTimeout(ctx, 10*time.Minute)
	defer cancel()
	args := []string{f.Name()}
	if check {
		args = append(args, "--check")
	}
	cmd := exec.CommandContext(ctx, p.Binary, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	cmd.Cancel = func() error { return syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL) }
	cmd.WaitDelay = 5 * time.Second
	output := &limitedOutput{limit: 1 << 20}
	cmd.Stdout = output
	if e = cmd.Run(); e != nil {
		return Prepared{}, denied
	}
	var wire struct {
		Root string `json:"root"`
		Prepared
	}
	if e = json.Unmarshal(output.Bytes(), &wire); e != nil {
		return Prepared{}, denied
	}
	result := wire.Prepared
	result.Root = wire.Root
	if result.Recipient != recipient || result.Model != p.Profile.Model {
		return Prepared{}, denied
	}
	result.Query = query
	return result, nil
}
func (p Preparer) Access(scope, recipient string) (Access, error) {
	if scope == "" || recipient == "" || p.Profile.Recipient != recipient {
		return Access{}, denied
	}
	return Access{Scope: scope, Recipient: recipient, Profile: p.Profile,
		Prepare: func(r *http.Request, q string) (Prepared, error) { return p.execute(r.Context(), recipient, q, false) },
		Check: func(r *http.Request, old Prepared) error {
			current, e := p.execute(r.Context(), recipient, old.Query, true)
			if e != nil || current.Key != old.Key || current.View != old.View || current.Model != old.Model || current.Recipient != old.Recipient || !reflect.DeepEqual(current.Records, old.Records) {
				return denied
			}
			return nil
		},
	}, nil
}
