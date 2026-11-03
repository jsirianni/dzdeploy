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

The configuration-repository baseline test is omitted because its server configuration tree is not part of this tooling repository. All other existing Go tests are retained.

The existing portable packager supports Windows and Linux clients on amd64 and arm64, and includes a Windows amd64 host companion, bootstrap script, example configuration, documentation, and internal checksums.

## Configuration repository

Server configuration remains in `dayz_config`. Run the client from that checkout, or pass its path with the existing `--repo` option, for example `dzdeploy status nasdara --repo /path/to/dayz_config`. The client reads `deploy.yaml` from that configuration repository by default and still requires its tracked target definitions and server files.

See [deployment documentation](docs/deployment.md) and [operator workflows](docs/operator-workflows.md). These documents, example configuration, and existing bootstrap/test scripts are copied from the source repository and retain its server-specific operational context. CI references in the copied documentation describe the source repository; this repository has no workflows.

Keep populated configuration, private keys, credentials, and compiled binaries out of Git.
