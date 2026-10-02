# Public native memory must enroll through each user's Aimee

Decision, 2 October 2026: the first public GitHub release belongs to
`RakuenSoftware/aimee` and must work for anyone running the latest Aimee. It
must not depend on a separately provisioned preview account or a Rakuen-owned
endpoint.

The existing Aimee flow already issues a short-lived, single-device invitation
in **Settings → Clients**. `aimee remote set URL INVITATION` pins the server
certificate, creates a client key locally, sends a CSR, and receives a
certificate tied to that user's account. Aimee owns invitation issuance,
expiry, one-use redemption, grants and revocation. The plugin uses this
identity; it does not create a second account system or ask for an unrelated
long-lived scoped token. The standard Aimee thin client alone performs
enrollment with `aimee remote set URL INVITATION`. Once enrolled,
`aimee-native connect-aimee` uses that thin-client identity to check
`/v1/native/bootstrap`; it rejects absent or exposed credential files. This
plugin connection command is **not in the previously signed
0.2.2 wheel**.

The server half is not done. The previous authenticated native bridge has been
ported onto current public `aimee` main in branch
`feature/native-delivery-current` ([draft PR #3001](https://github.com/RakuenSoftware/aimee/pull/3001)); it is disabled until a private Unix delivery
socket is configured. Current public Aimee releases have neither those native
routes nor the private publisher, preparer and delivery processes. The present
private service also requires an operator-maintained principal-to-release-policy
binding and explicit model profiles. That static preview configuration cannot
serve arbitrary newly enrolled users. Aimee's normal single-user install has
personal memory without a KB, while the preview preparer reads a separately
published image; the self-host path must connect the personal memory authority
to preparation as well. Enrollment alone cannot supply missing source records.

Release acceptance requires the following end-to-end behavior on an ordinary
fresh Aimee install **without a KB**, with no preview infrastructure:

1. Aimee issues the normal short-lived client invitation. The installed Aimee
   thin client redeems it with `aimee remote set`, creating a certificate-bound
   identity; `connect-aimee` uses that existing enrollment. A copied bearer
   without the certificate fails.
2. The installed Aimee server exposes the native API through its normal
   authorization path and starts the delivery/preparation service. The service
   derives the recipient, source view and release policy from the authenticated
   Aimee account rather than an operator-edited bindings file. It prepares only
   records that account may read, for a model identity the user has installed.
3. Selection, download and final approval work after an update. Another user's
   invitation or publication cannot be used, and revoking the enrolled client
   blocks fresh selection and lease approval.
4. A clean, supported CUDA and HIP install consumes its own Aimee memory
   through the public wheel. The exact released wheel, server image and source
   commit pass a no-memory control, authorized memory, revision, revocation and
   cross-user isolation checks. A clean public `[gguf]` install resolves the
   pinned dependency from the public Aimee GitHub Release.

Current verification: the Rust launcher suite passes in a Linux build container
(23 tests total), including complete and incomplete local enrollment fixtures.
The release-mode launcher also passed a local HTTPS bootstrap with a mock Aimee
server that required the thin client's mTLS certificate and enrolled bearer;
an exposed private-key file was refused before connection. This checks the
credential handoff, not an ordinary Aimee deployment.
The ported C bridge compiles against current Aimee main. The current-main
compatibility branch now restores Aimee-owned explicit release policy, scoped
source export and restricted search contracts. The private publisher, read
ingress and delivery Go packages compile and pass tests against that branch.
The restricted search and selected personal export also pass against a
disposable PostgreSQL instance, including multi-record composition, filter
before limit, expired/retired exclusion and empty-selection refusal. The
unchanged Aimee CLI uses its established enrollment path; a full server build
needed an unrelated const-qualifier warning relaxed locally under `-Werror`.
These results do not establish the fresh-install service behavior in items 2–4:
an ordinary install still has no service that derives the enrolled owner's
publication and model profiles, and the signed wheel predates `connect-aimee`.
Four Go server components have been built reproducibly from the current Aimee
and aimee-qwen branches, with source commits and SHA-256 hashes recorded in a
private staging directory. A stripped `native-prepare` Linux binary also builds
and starts. Neither build includes a self-hosted encoder/model installation or
an automatic publication service; these are build artifacts, not a public
release candidate.
The old signed wheel remains useful as controlled-preview evidence but cannot
be relabeled a general public release.

The exact public-build wheel's supplemental Gemma 4 12B AMD probe subsequently
passed, as did its earlier RTX 5080 probe. These demonstrate the packaged
consumer, not the missing ordinary-user server installation path.
