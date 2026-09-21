package sparse

import (
	"bytes"
	"encoding/json"
	"fmt"
	"github.com/JBailes/aimee/server-go/modules/memory/readcontract"
	"io"
	"reflect"
	"sort"
	"strconv"
)

// SearchRestriction is the Aimee-owned wire contract, not a local grant.
type SearchRestriction = readcontract.SearchRestriction

func RestrictSearch(a Authorization, namespace string) (SearchRestriction, error) {
	raw, err := json.Marshal(a)
	if err != nil {
		return SearchRestriction{}, err
	}
	r := SearchRestriction{Version: 1, Namespace: namespace, Authorization: digest(raw), IDs: []int64{}}
	for _, ref := range a.Records {
		if ref.Namespace != namespace {
			continue
		}
		id, e := strconv.ParseInt(ref.ID, 10, 64)
		if e != nil || strconv.FormatInt(id, 10) != ref.ID {
			return r, fmt.Errorf("upstream requires canonical numeric IDs")
		}
		r.IDs = append(r.IDs, id)
	}
	sort.Slice(r.IDs, func(i, j int) bool { return r.IDs[i] < r.IDs[j] })
	return r, r.Validate()
}
func validateRestrictionReceipt(raw json.RawMessage, a Authorization) error {
	var r SearchRestriction
	d := json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	if err := d.Decode(&r); err != nil {
		return err
	}
	if d.Decode(&struct{}{}) != io.EOF {
		return fmt.Errorf("trailing restriction")
	}
	want, err := RestrictSearch(a, r.Namespace)
	if err != nil || !reflect.DeepEqual(r, want) {
		return fmt.Errorf("upstream restriction mismatch")
	}
	return nil
}
