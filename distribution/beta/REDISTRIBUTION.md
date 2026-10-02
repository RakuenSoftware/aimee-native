# Distribution review status

The release-5 artifact set inherits the unchanged model/runtime/launcher dependency
inventory and notices from the controlled-preview review. The only release-5
changes are the private compiled activation bridge and Rust read/residency logic;
Cargo.lock and runtime packages did not change. See:

- docs/validation/artifacts/native-live-release-20260926/package-review.json
- docs/validation/artifacts/native-streaming-20260926/release-delta-review.json
- docs/validation/artifacts/native-streaming-20260926/manifest.json
- distribution/container/licenses/
- distribution/container/runtime-requirements.lock

The private consumer audit and notice inventory pass for the tested preview.
Model notice identifies the upstream Gemma artifact and local Q8 conversion.
Client allowlists omit the private compiler and all enrollment/signing secrets.
Known dependency limitations remain in package-review.json; later performance
validation does not waive them or create a security certification.

External redistribution is NOT approved by this record. Before distributing the
whole OCI image externally, produce a component-by-component source/notice
fulfillment inventory for its OS and binary dependencies, including corresponding
source/build material where applicable. Verify the exact redistributed model
license/version and redistribution channel against upstream terms; preserve
attribution and conversion notices. The existing inventory alone is not evidence
that every external-distribution obligation has been fulfilled. This release has
no completed source-offer bundle, and this document does not pretend otherwise.

The beta can continue within the already reviewed controlled private scope.
Public-release clearance is a remaining release gate, not a runtime test failure.

The exact image now also has an OS binary-to-source-package inventory in
os-source-inventory-release-5.tsv, collected with dpkg-query from release 5.
It records package and source versions; it is not the corresponding-source bundle.
