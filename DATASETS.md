# Reference data and archived research

The AGPL license covers Aimee Native source. It does not replace upstream data,
model or third-party code terms. No foundation-model weights are distributed by
the current release. Download weights independently under their publisher's terms.

## Public reference snapshots

The [v1 inventory](knowledge/general-v1/README.md) and
[v2 inventory](knowledge/general-v2/README.md) record transformations, fields,
retrieval times, exact input hashes and experimental limitations. Retain their
provenance and this attribution when redistributing derived reference corpora.

| Source | Attribution and terms | Changes here |
| --- | --- | --- |
| GeoNames | Credit [GeoNames](https://www.geonames.org/), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); [source information](https://www.geonames.org/export/) | Cities500 snapshot projected into canonical records and alternate cues; original dump/readme preserved. |
| IANA service registry | [IANA protocol registries, CC0](https://www.iana.org/help/licensing-terms) | Service names, ports and transports consolidated; raw public registry snapshot also retained. |
| World Bank country API | Credit World Bank, adapted country/economy data; [data terms](https://data.worldbank.org/summary-terms-of-use), default CC BY 4.0 subject to stated exceptions and additional terms | Aggregate regions excluded; economy identifiers and classifications retained. No third-party indicator series imported. |
| NASA Exoplanet Archive | Operated by Caltech under NASA's Exoplanet Exploration Program; [acknowledgment and citation guidance](https://exoplanetarchive.ipac.caltech.edu/docs/acknowledge.html) | Public composite-parameter TAP rows projected into factual records; no paper full texts or images. Preserve per-record provenance and cite the Archive when using these data. |
| NIST CODATA 2022 | Tiesinga, Mohr, Newell and Taylor, NIST, [database version 9.0](https://physics.nist.gov/cuu/Reference/versioncon.shtml); [NIST use terms](https://www.nist.gov/copyrights-disclaimers) | Complete public ASCII table projected into quantities, units and uncertainties; optional normalization is a separately identified experiment. No endorsement by NIST is implied. |

NIST's general permission applies to information not marked as copyrighted;
its separate [SRD policy](https://www.nist.gov/open/copyright-fair-use-and-licensing-statements-srd-data-software-and-technical-series-publications)
distinguishes protected Standard Reference Data. The retained constants input
has no separate copyright marking. These notices do not assert that all SRD is
public domain or relicense upstream databases under AGPL.

These are historical factual snapshots, not a live or certified reference
service. They carry their upstream limitations and no project warranty. Public
data possession does not authorize access to private Aimee memory.

## Historical evidence and dependency snapshots

Research reports retain original bytes, runtime paths and hashes. Archived
candidate wheels may retain their original proprietary metadata; they are
historical evidence, not the AGPL release wheels. New release manifests identify
the supported artifacts explicitly. Historical tensor fixtures are experiment
outputs, not foundation-model checkpoints.

The separately owned Aimee source snapshot is documented in
[its provenance record](dependencies/aimee-memory-source-2026-09-21.json).
Its base revision `912207eecb9c010e738ae7e36678eeae34ba2d73` is AGPL-3.0-only;
the [AGPL text](LICENSE) accompanies this repository. The original archive lacks
a license member and remains unchanged to preserve its recorded hash. Current
enrolled serving depends on the released Aimee API rather than this research
snapshot. Dependency code is not relicensed by these notices.
