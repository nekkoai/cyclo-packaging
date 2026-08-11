# Cyclo Packaging

Standalone Ubuntu/Debian packaging for the Cyclo suite. This repository owns
packaging policy and reproducible source selections; it deliberately does not
place `debian/` directories in the Cyclo, DComp, or provider-pooler source
repositories.

## Components

| Package | Upstream | Purpose |
| --- | --- | --- |
| `dcomp` | DComp | Docker component lifecycle command required by Cyclo |
| `cyclo-agent` | Cyclo | Host CLI, immutable runtime resources, and system host.conf conffile |
| `cyclo-provider-pooler` | Provider Pooler | Docker build context for the optional quota-aware Provider component |

The source lock records each upstream URL, branch, immutable commit, and Debian
package version. `tools/fetch-sources` refuses a checkout whose origin or commit
differs from the lock.

## Build prerequisites

Build on Ubuntu with `git`, `dpkg-dev`, and each package's declared build
dependencies. `dcomp` currently requires Go 1.25 or newer; Ubuntu 24.04's
archive Go toolchain is older, so build it on an image that provides Go 1.25+
or deliberately provision that toolchain in the builder.

The runtime packages deliberately do not start services, alter Docker-group
membership, create users, or create Docker resources. The deployment APT
repository must publish `dcomp` beside `cyclo-agent`, because Cyclo requires
DComp machine API 1 at runtime.

## Workflow

Fetch the exact locked source checkouts:

```sh
make fetch
```

Build every package into `artifacts/`, or build one package:

```sh
make build
make cyclo-agent
make dcomp
make cyclo-provider-pooler
```

`tools/build-packages` stages each source with `git archive`, overlays only this
repository's `packages/NAME/debian/`, checks the changelog version against the
lock, and runs `dpkg-buildpackage --build=binary`. It never writes packaging
files into an upstream checkout.

Run repository validation:

```sh
make test
```

## GitHub build artifacts

The **Build latest Cyclo Debian packages** workflow is manual-only. Its dispatch
form accepts a branch name for Cyclo, DComp, and provider-pooler; each input
defaults to `main`. If an upstream has not renamed its locked default branch,
a requested `main` falls back explicitly to that locked branch (currently
DComp's `master`). It resolves the resulting branch tips, derives the
corresponding Debian versions, builds the complete suite, and uploads the `.deb`,
`.ddeb`, `.buildinfo`, `.changes`, resolved `sources.lock.json`, generated
packaging-version patch, checksums, and an unsigned `apt-repository/` as one
GitHub Actions artifact. It does not commit the refreshed lock or changelogs
back to this repository.

Use the same refresh locally before an intentional lock update:

```sh
make refresh-latest
make build
```

## Updating an upstream

1. Review the upstream commit and update its entry in `sources.lock.json`.
2. Update the matching package changelog version; prerelease snapshots use
   `~gitYYYYMMDD.SHORTSHA-1` so an eventual upstream release sorts newer.
3. Run `make PACKAGE` and inspect the `.deb`, `.buildinfo`, and `.changes` in
   `artifacts/PACKAGE/`.
4. Update package tests or documentation for any resource/layout change.

## Package boundaries

- `dcomp` installs `/usr/bin/dcomp` and `/usr/bin/dcomp-healthcheck`.
- `cyclo-agent` owns `/etc/cyclo/host.conf`, which stays comment-only by
default; credentials remain in a per-user Docker volume.
- `cyclo-provider-pooler` installs its complete Docker context at
  `/usr/share/cyclo/components/provider-pooler`. It never edits `host.conf`:
  account IDs, provider ordering, and pool policy belong to the operator.
