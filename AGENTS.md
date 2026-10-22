# Agent Entry Point

Read `README.md`, `ENVIRONMENT.md`, `UPSTREAM.md`, and `manifest.json` first.

This is a source backport and local package-building toolkit for one exact
Ubuntu 18.04 / amd64 / NTS PHP 7.2 baseline. Matching image names do not prove
package or executable compatibility.

- Begin with `python3 tools/verify.py baseline`. It only reads the host baseline.
  OS, architecture, package revision, or executable hash mismatch stops reuse.
- The release's `.deb` files are unpatched Ubuntu build inputs, not security
  update packages. Build locally in a separate Bionic amd64 environment.
- The root manifest is a build template with no patched package hashes.
  For `packages`, `smoke`, and `installed`, pass `--manifest` pointing to the
  manifest produced by a completed local build. Never bypass this requirement.
- Source preparation and building never install packages, connect to a DB,
  or restart services. Do not install missing dependencies on a service host
  without an explicit instruction for that host.
- CLI smoke uses synthetic data, `-n`, and temporary session files. It does
  not prove shared extensions, application behavior, or web E2E acceptance.
- Install, restart, or rollback needs an explicitly assigned target and
  instruction. Validate Stage first, preserve configuration and extensions,
  and use the same verified artifacts for production.
- Never run RCE/OOM/fatal probes against shared FPM pools.
- Verify running FPM master/worker executable hashes, not just disk versions.
  Old CLI processes cause a nonzero result; never stop/rerun jobs without
  checking ownership, duplicate processing, and data effects.
- Keep credentials, company names, host/image inventories, private paths,
  operational history, raw logs, and binary build output out of Git and issues.
- Preserve the upstream patch bytes and source hashes. New baselines require
  their own port, manifest, isolated validation, and compatibility review.
