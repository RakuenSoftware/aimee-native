# Controlled native-memory beta

The private beta uses the signed `gemma4-12b-q8-native` release, sequence 5.
Its manifest SHA-256 is
`d56c92bfade06bf91ad6cb713d04fe791815b65350f4414f91cd82514554960b`.
The immutable runtime digest is
`sha256:4d901b1cc0e5a203dcd0b19d53aa4a2dc852e6027f6c48c80af1637822cb4831`.

## Supported profile

Linux x86-64, the certified ROCm 7.2.3 runtime/host combination, two RX 7900 XTXs,
Gemma 4 12B Q8_0, tensor parallelism 2, Podman and the signed runtime profile.
The container has a 48-GiB host-memory limit. Reserve additional host memory for
Podman, download/unpack and the OS. This profile is not certification for other
GPUs, CUDA, macOS, Windows, arbitrary models or arbitrary vLLM versions.
The original delivery profile uses a 2,048-position conversation; the 8,192-position
SWE experiment is a separately tested engineering configuration, not an automatic
change to the signed beta profile.

## User workflow

Obtain the enrolled launcher, pinned release trust and approved account identity
from the operator. The server-side compiler is not installed on the client.

```
aimee-native connect https://YOUR-AIMEE-ENDPOINT
aimee-native install gemma4-12b-q8-native
aimee-native run
```

`connect` reads the account bearer from stdin. Use `--ca-file` and
`--client-identity` for an operator-issued private CA/mTLS enrollment, where
required. Do not put credentials in command arguments or shared configuration.
The launcher owns authenticated delivery, container startup and the memory broker.
Serve the text API on loopback; remote access needs the application's authenticated
front end. Clients receive only the operator-approved publication, not the whole KB.

Run `aimee-native install gemma4-12b-q8-native` for a signed update;
`aimee-native rollback` restores the prior installed release. Rollback does not
lower the release-sequence high-water mark or restore withdrawn memory authority.
Stop the launcher before changing runtime versions. Keep the previous artifact
set until update and canary checks pass.

## Acceptance and support

- Exact release: 352/352 serving checks, 6/6 signed installation/update/rollback
  canaries; all source tensor bytes retained.
- Additional real-model comparison: 336/336 answers, native/text median response
  308/664 ms and first content 66/377 ms. Fixed synthetic fixture; no universal
  latency promise.
- Cold loading remains milliseconds: 3.50 ms small, 31.44 ms wide in the follow-up.
  Resident lookup and native activation are different timings.
- Native state uses memory/device resources although it consumes no prompt tokens.
  New selections may need server-side preparation; first-use latency includes it.
- Admission pressure may return HTTP 429; retry with bounded backoff. Lost authority,
  inconsistent refresh or poisoned worker state must fail closed. Restart the
  managed runtime after a required-restart state; do not bypass authority checks.

Collect release ID, runtime image digest, sanitized error type, timestamps and
aggregate metrics for support. Keep private questions, memory contents, bearer
credentials and model artifacts out of shared reports.

## Distribution boundary

The existing restricted binary package excludes encoding/compiler implementations,
source databases, identity credentials and signing keys. vLLM is unmodified.
Packaging cannot prevent a recipient from inspecting binaries or usable tensors.

This is controlled private-preview documentation, not public redistribution
clearance. The dependency review below records the remaining external-release
requirements explicitly. No new endpoint, public repository, or public model
artifact was published by this work.
