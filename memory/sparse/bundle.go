package sparse

import (
	"archive/tar"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
)

// Export is an INTERNAL backup of all reachable objects, including historical
// and out-of-scope records. Never distribute it as an authorization-filtered KB.
// Use CompileAuthorized into a fresh destination before model-facing export.
func (s Store) Export(id string, w io.Writer) error {
	objects := map[string]bool{}
	seen := map[string]bool{}
	var walk func(string) error
	walk = func(hash string) error {
		if hash == "" || seen[hash] {
			return nil
		}
		if len(seen) > 4096 {
			return fmt.Errorf("excessive bundle ancestry")
		}
		seen[hash] = true
		m, err := s.manifest(hash)
		if err != nil {
			return err
		}
		objects[hash] = true
		objects[m.Index] = true
		objects[m.Data] = true
		if err = walk(m.Upstream); err != nil {
			return err
		}
		return walk(m.Previous)
	}
	if err := walk(id); err != nil {
		return err
	}
	v, err := s.Open(id)
	if err != nil {
		return err
	}
	v.Close()
	tw := tar.NewWriter(w)
	if err = tw.WriteHeader(&tar.Header{Name: "VIEW", Mode: 0600, Size: int64(len(id)), Typeflag: tar.TypeReg}); err != nil {
		return err
	}
	if _, err = io.WriteString(tw, id); err != nil {
		return err
	}
	names := make([]string, 0, len(objects))
	for hash := range objects {
		names = append(names, hash)
	}
	sort.Strings(names)
	for _, hash := range names {
		p, err := s.object(hash)
		if err != nil {
			return err
		}
		f, err := os.Open(p)
		if err != nil {
			return err
		}
		stat, err := f.Stat()
		if err != nil {
			f.Close()
			return err
		}
		if err = tw.WriteHeader(&tar.Header{Name: "objects/" + hash, Mode: 0600, Size: stat.Size(), Typeflag: tar.TypeReg}); err != nil {
			f.Close()
			return err
		}
		h := sha256.New()
		_, err = io.Copy(io.MultiWriter(tw, h), f)
		f.Close()
		if err != nil {
			return err
		}
		if hex.EncodeToString(h.Sum(nil)) != hash {
			return fmt.Errorf("bundle object checksum mismatch")
		}
	}
	return tw.Close()
}

// Import verifies content hashes and view lineage without publishing. A corrupt
// or truncated bundle may leave unreachable objects, but never changes CURRENT.
func (s Store) Import(r io.Reader) (string, error) {
	if err := os.MkdirAll(filepath.Join(s.Root, "objects"), 0700); err != nil {
		return "", err
	}
	tr := tar.NewReader(r)
	head := ""
	seen := map[string]bool{}
	for {
		h, err := tr.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return "", err
		}
		if h.Typeflag != tar.TypeReg || seen[h.Name] {
			return "", fmt.Errorf("unsupported or duplicate bundle member")
		}
		seen[h.Name] = true
		if h.Name == "VIEW" {
			if h.Size != 64 {
				return "", fmt.Errorf("invalid bundle view")
			}
			b, err := io.ReadAll(tr)
			if err != nil {
				return "", err
			}
			head = string(b)
			if !digestPattern.MatchString(head) {
				return "", fmt.Errorf("invalid bundle digest")
			}
			continue
		}
		if len(h.Name) != len("objects/")+64 || h.Name[:8] != "objects/" || !digestPattern.MatchString(h.Name[8:]) || h.Size < 0 {
			return "", fmt.Errorf("invalid bundle object path")
		}
		f, err := os.CreateTemp(filepath.Join(s.Root, "objects"), ".import-")
		if err != nil {
			return "", err
		}
		hash := sha256.New()
		n, copyErr := io.Copy(io.MultiWriter(f, hash), tr)
		if copyErr != nil || n != h.Size || hex.EncodeToString(hash.Sum(nil)) != h.Name[8:] {
			f.Close()
			os.Remove(f.Name())
			return "", fmt.Errorf("bundle payload checksum/length mismatch")
		}
		err = s.install(f, h.Name[8:])
		os.Remove(f.Name())
		if err != nil {
			return "", err
		}
	}
	if head == "" {
		return "", fmt.Errorf("bundle has no view")
	}
	v, err := s.Open(head)
	if err != nil {
		return "", err
	}
	v.Close()
	return head, nil
}
