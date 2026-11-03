# dzdeploy

Go tooling for deploying DayZ server configuration over SSH/SFTP from Windows and Linux clients to Windows hosts.

Copied from [jsirianni/dayz_config](https://github.com/jsirianni/dayz_config/tree/6424d5f79ee92c9ba745cff24862b41e0d5eb649) at commit `6424d5f79ee92c9ba745cff24862b41e0d5eb649`. The Go module and internal import paths use `github.com/jsirianni/dzdeploy`; application behavior is unchanged.

## Build and test

Use the toolchain selected by `go.mod` (Go 1.27.3):

```text
go build -o .tools/bin/ ./cmd/dzdeploy
go test ./...
go vet ./...
go run ./cmd/dzdeploy-package --os windows --arch amd64
```

The root Makefile provides `build`, `check`, `test`, and `tidy` targets. [GitHub Actions](https://github.com/jsirianni/dzdeploy/actions/workflows/dzdeploy.yml) runs the existing Windows/Linux build and test jobs, portable package artifacts, Windows SSH and operator integration, race tests, and vulnerability checks on pushes to `main` and pull requests.

The configuration-repository baseline test is omitted because its server configuration tree is not part of this tooling repository. All other existing Go tests are retained.

The existing portable packager supports Windows and Linux clients on amd64 and arm64, and includes a Windows amd64 host companion, bootstrap script, example configuration, documentation, and internal checksums.

## Releases

Pushing a stable `vMAJOR.MINOR.PATCH` tag (for example, `v1.0.0`) runs the [release workflow](https://github.com/jsirianni/dzdeploy/actions/workflows/release.yml). After tests, vet, GoReleaser configuration checks, and a snapshot build pass for that commit, pinned GoReleaser OSS publishes a [GitHub Release](https://github.com/jsirianni/dzdeploy/releases) using the repository's `GITHUB_TOKEN`. Tags with prerelease suffixes or leading zeros are rejected. Tag a reviewed commit from `main` after its CI passes.

To publish a reviewed `main` commit after its CI passes, choose an unused version and push its tag (replace `v1.0.0` below):

```text
git switch main
git pull --ff-only
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

Each release contains four `dzdeploy_<version>_<linux|windows>_<amd64|arm64>.zip` archives and `checksums.txt` with their SHA-256 hashes. Extract the entire archive: it contains the client, `agents/windows-amd64/dzdeploy.exe`, bootstrap script, example YAML, and operator documentation. Keep that companion beside Linux and Windows arm64 clients; Windows amd64 clients upload their own executable. The archives contain no populated `deploy.yaml`, private keys, credentials, or game files.

Pull requests and manual workflow runs build snapshots without publishing; only a tag push can publish a release. To check the same packaging locally with GoReleaser OSS 2.19.0:

```text
goreleaser check
goreleaser release --snapshot --clean
```

Output is written to the ignored `.tools/releases/` directory. Verify a downloaded ZIP against the matching entry in `checksums.txt` before extracting it (`sha256sum --ignore-missing --check checksums.txt` with the downloaded ZIP beside the checksum file on Linux, or `Get-FileHash -Algorithm SHA256 <archive.zip>` on Windows). Release checksums cover the complete archives; the existing source packager continues to produce its own per-file `checksums.json` format.

## Configuration repository

Server configuration remains in `dayz_config`. Run the client from that checkout, or pass its path with the existing `--repo` option, for example `dzdeploy status nasdara --repo /path/to/dayz_config`. The client reads `deploy.yaml` from that configuration repository by default and still requires its tracked target definitions and server files.

See [deployment documentation](docs/deployment.md) and [operator workflows](docs/operator-workflows.md). These documents, example configuration, and existing bootstrap/test scripts are copied from the source repository and retain its server-specific operational context. The existing dzdeploy CI workflow, root Makefile, and root scripts are also copied from that revision.

Keep populated configuration, private keys, credentials, and compiled binaries out of Git.
