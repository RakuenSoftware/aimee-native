package sparse

import (
	"crypto/ed25519"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// Publisher reconciles an Aimee-approved source into a recipient delivery.
// It never creates permissions. Run it outside the model's OS identity with
// an independently issued grant. Source/approval failure withdraws old bytes.
// CURRENT and the grant should be replaced atomically by the control plane.
type Publisher struct {
	Source       Store
	Delivery     Delivery
	ApprovalPath string
	PublicKey    ed25519.PublicKey
	Subject      string
	PolicyEpoch  string
	ReaderGID    int
}
type PublicationResult struct {
	TransferredBytes int64   `json:"transferred_bytes,omitempty"`
	Upserts          int     `json:"upserts,omitempty"`
	Removals         int     `json:"removals,omitempty"`
	CueEdits         int     `json:"cue_edits,omitempty"`
	ReusedBytes      int64   `json:"reused_bytes,omitempty"`
	ApplyMillis      float64 `json:"apply_ms,omitempty"`
	State            string  `json:"state"`
	View             string  `json:"view,omitempty"`
	Reason           string  `json:"reason,omitempty"`
	CopiedBytes      int64   `json:"copied_bytes,omitempty"`
}

func (p Publisher) Reconcile(now time.Time) (PublicationResult, error) {
	started := time.Now()
	if p.Subject == "" || p.PolicyEpoch == "" || len(p.PublicKey) != ed25519.PublicKeySize {
		return PublicationResult{}, fmt.Errorf("trusted publisher binding required")
	}
	if err := p.Delivery.initialize(p.ReaderGID); err != nil {
		return PublicationResult{}, err
	}
	current, err := p.Delivery.current()
	if err != nil {
		return PublicationResult{}, err
	}
	withdraw := func(reason string) (PublicationResult, error) {
		_, e := p.Delivery.Withdraw(current)
		return PublicationResult{State: "withdrawn", Reason: reason}, e
	}
	raw, err := os.ReadFile(p.ApprovalPath)
	if err != nil {
		return withdraw("approval_unavailable")
	}
	var signed SignedAuthorization
	if json.Unmarshal(raw, &signed) != nil {
		return withdraw("approval_invalid")
	}
	a, err := VerifyAuthorization(signed, p.PublicKey, p.Subject, p.PolicyEpoch, now)
	if err != nil {
		return withdraw("approval_rejected")
	}
	source, err := p.Source.Current()
	if err != nil || source != a.SourceView {
		return withdraw("source_approval_mismatch")
	}
	// Even an unchanged grant must have a live, intact source. Cached local bytes
	// must never hide a retirement or a broken authoritative publication.
	v, err := p.Source.Open(source)
	if err != nil {
		return withdraw("source_unavailable")
	}
	for _, approved := range a.Records {
		r, e := v.Get(approved.Ref, grantMap(a), now)
		if e != nil || AuthorizeRecord(r) != approved {
			v.Close()
			return withdraw("source_changed")
		}
	}
	v.Close()
	if current != "" {
		live, e := (Store{p.Delivery.Root}).PinPublished(nil)
		if e == nil {
			same := live.Publication == signed.Digest()
			live.Close()
			if same {
				_, e = p.Delivery.Prune(current)
				return PublicationResult{State: "unchanged", View: current}, e
			}
		}
	}
	// Temporary construction is publisher-private, never a recipient staging area.
	tmp, err := os.MkdirTemp(filepath.Dir(p.Source.Root), ".publication-")
	if err != nil {
		return withdraw("staging_unavailable")
	}
	defer os.RemoveAll(tmp)
	dst := Store{filepath.Join(tmp, "compiled")}
	_, err = p.Source.CompileAuthorized(dst, signed, p.PublicKey, p.Subject, p.PolicyEpoch, now)
	if err != nil {
		return withdraw("compilation_failed")
	}
	// Recheck after compilation to avoid publishing stale approval/source pairs.
	latest, e := os.ReadFile(p.ApprovalPath)
	head, he := p.Source.Current()
	if e != nil || he != nil || string(latest) != string(raw) || head != source {
		return withdraw("source_changed_during_compile")
	}
	if _, e := VerifyAuthorization(signed, p.PublicKey, p.Subject, p.PolicyEpoch, now.Add(time.Since(started))); e != nil {
		return withdraw("approval_expired_during_compile")
	}
	stale := false
	result, err := p.Delivery.install(dst, current, p.ReaderGID, func() error {
		latest, e := os.ReadFile(p.ApprovalPath)
		head, he := p.Source.Current()
		_, ve := VerifyAuthorization(signed, p.PublicKey, p.Subject, p.PolicyEpoch, now.Add(time.Since(started)))
		if e != nil || he != nil || ve != nil || string(latest) != string(raw) || head != source {
			stale = true
			return fmt.Errorf("approval changed before publication commit")
		}
		return nil
	})
	if stale {
		return withdraw("approval_changed_before_commit")
	}
	if err != nil {
		return PublicationResult{}, err
	}
	return PublicationResult{State: "installed", View: result.View, CopiedBytes: result.CopiedBytes}, nil
}
