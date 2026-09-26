package nativepublication

// This boundary accepts identity only from the kernel-authenticated Aimee
// frontend. The frontend has already checked bearer, certificate and capability
// authority. Release decisions remain in Aimee's execution-policy package.
import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	policy "github.com/JBailes/aimee/server-go/modules/execution-policy"
	"io"
	"net"
	"net/http"
	"os"
	"syscall"
	"time"
)

type peerKey struct{}

// PeerContext must be installed directly on http.Server.ConnContext, never
// populated from HTTP headers or a network proxy's asserted uid.
func PeerContext(ctx context.Context, c net.Conn) context.Context {
	u, ok := c.(*net.UnixConn)
	if !ok {
		return ctx
	}
	raw, e := u.SyscallConn()
	if e != nil {
		return ctx
	}
	var cred *syscall.Ucred
	e = raw.Control(func(fd uintptr) { cred, _ = syscall.GetsockoptUcred(int(fd), syscall.SOL_SOCKET, syscall.SO_PEERCRED) })
	if e != nil || cred == nil {
		return ctx
	}
	return context.WithValue(ctx, peerKey{}, cred.Uid)
}

type Binding struct {
	Principal     string   `json:"principal"`
	ReleasePolicy string   `json:"release_policy"`
	PublisherUID  uint32   `json:"publisher_uid"`
	Preparer      Preparer `json:"preparer"`
}
type Authority struct {
	Bindings    string
	FrontendUID uint32
}
type bindingFile struct {
	Schema   int       `json:"schema"`
	Bindings []Binding `json:"bindings"`
}

func readOwnedJSON(path string, into any) error {
	fd, e := syscall.Open(path, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if e != nil {
		return e
	}
	f := os.NewFile(uintptr(fd), path)
	defer f.Close()
	st, e := f.Stat()
	if e != nil {
		return e
	}
	if !st.Mode().IsRegular() || st.Mode().Perm()&0022 != 0 || st.Sys().(*syscall.Stat_t).Uid != uint32(os.Geteuid()) || st.Size() > 4<<20 {
		return denied
	}
	b, e := io.ReadAll(io.LimitReader(f, (4<<20)+1))
	if e != nil || len(b) > 4<<20 {
		return denied
	}
	d := json.NewDecoder(bytes.NewReader(b))
	d.DisallowUnknownFields()
	if e = d.Decode(into); e != nil {
		return e
	}
	if d.Decode(&struct{}{}) != io.EOF {
		return denied
	}
	return nil
}

func (a Authority) Resolve(r *http.Request) (Access, error) {
	uid, ok := r.Context().Value(peerKey{}).(uint32)
	if !ok || uid != a.FrontendUID {
		return Access{}, denied
	}
	// The bridge hex-encodes the attested principal and discards incoming client
	// headers. Duplicate identity fields are never accepted.
	values := r.Header.Values("X-Aimee-Native-Principal")
	if len(values) != 1 || len(values[0]) > 2048 {
		return Access{}, denied
	}
	principal, e := hex.DecodeString(values[0])
	if e != nil || len(principal) == 0 {
		return Access{}, denied
	}
	var registry bindingFile
	if readOwnedJSON(a.Bindings, &registry) != nil || registry.Schema != 1 || len(registry.Bindings) > 4096 {
		return Access{}, denied
	}
	var selected *Binding
	seen := map[string]bool{}
	for i := range registry.Bindings {
		b := &registry.Bindings[i]
		if b.Principal == "" || seen[b.Principal] {
			return Access{}, denied
		}
		seen[b.Principal] = true
		if b.Principal == string(principal) {
			selected = b
		}
	}
	if selected == nil {
		return Access{}, denied
	}
	b := *selected
	var release policy.MemoryReleasePolicy
	if readOwnedJSON(b.ReleasePolicy, &release) != nil || release.Validate(b.Preparer.Profile.Recipient, b.PublisherUID, time.Now()) != nil {
		return Access{}, denied
	}
	// Bind leases to every routing input as well as the current release, so a
	// model, template or recipient change cannot reuse an earlier capability.
	wire, _ := json.Marshal(struct {
		Binding Binding
		Release string
	}{b, release.Digest()})
	digest := sha256.Sum256(wire)
	access, e := b.Preparer.Access(hex.EncodeToString(digest[:]), release.Recipient)
	if e != nil {
		return Access{}, e
	}
	check := access.Check
	access.Check = func(req *http.Request, p Prepared) error {
		current, e := a.Resolve(req)
		if e != nil || current.Scope != access.Scope {
			return errors.New("native authority changed")
		}
		return check(req, p)
	}
	return access, nil
}
