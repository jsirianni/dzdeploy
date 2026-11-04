# Linux DEB and RPM packages

Releases containing this change add DEB and RPM packages for amd64 and arm64 alongside the four portable ZIPs. **v0.1.0 remains ZIP-only**; choose a later published version that includes these assets. All eight assets are listed in the release's SHA-256 `checksums.txt`.

Use a specific reviewed version, never an unpinned latest download. Go and Python are not needed. Packages depend on Git and CA certificates. The native package manager installs those dependencies.

## Download and verify

Replace `X.Y.Z` with an available stable release version. Run these commands in a dedicated download directory.

Debian/Ubuntu:

```bash
version=X.Y.Z
arch=$(dpkg --print-architecture) # amd64 or arm64
package="dzdeploy_${version}_${arch}.deb"
base="https://github.com/jsirianni/dzdeploy/releases/download/v${version}"
curl --fail --location "$base/$package" -o "$package"
curl --fail --location "$base/checksums.txt" -o checksums.txt
sha256sum --ignore-missing --check checksums.txt
sudo apt-get install "./$package"
```

RPM-based distributions, including AlmaLinux:

```bash
version=X.Y.Z
arch=$(uname -m) # x86_64 or aarch64
package="dzdeploy-${version}-1.${arch}.rpm"
base="https://github.com/jsirianni/dzdeploy/releases/download/v${version}"
curl --fail --location "$base/$package" -o "$package"
curl --fail --location "$base/checksums.txt" -o checksums.txt
sha256sum --ignore-missing --check checksums.txt
sudo dnf install "./$package"
```

Inspect installed metadata with `dpkg-query -s dzdeploy` or `rpm -qi dzdeploy`. In this client, `dzdeploy version` reports the protocol version; the package manager reports the release version.

## Layout and configuration checkout

`/usr/bin/dzdeploy` is a symlink to `/usr/lib/dzdeploy/linux_<amd64|arm64>/dzdeploy`. The matching Windows amd64 companion is at `agents/windows-amd64/dzdeploy.exe` beside that real executable. The client resolves its executable path when finding the companion, so no `agent_binary` override is needed. Both binaries come from the same release build.

The public bootstrap script is `/usr/share/dzdeploy/bootstrap-windows.ps1`. Example YAML and deployment/operator documentation are under `/usr/share/doc/dzdeploy/`. The example is a template, not an installed populated configuration file. No Linux agent service or package lifecycle hooks are installed.

Keep the existing ignored `deploy.yaml`, SSH keys, known hosts and `.deploy/` state in the configuration checkout. Packages never manage them. Run the client there, or use the existing `--repo` flag:

```bash
dzdeploy tools install --repo /path/to/dayz_config
dzdeploy validate all --repo /path/to/dayz_config
```

The configuration checkout must retain committed target definitions and server files. Deployment still enforces its clean-main gate. Installing or upgrading a client does not upgrade an enrolled Windows agent, connect to hosts, deploy, or restart a server; those are separate authorized operations.

## Upgrade and removal

Download and verify a newer pinned package exactly as above. Use `sudo apt-get install ./<new-package.deb>` or `sudo dnf upgrade ./<new-package.rpm>`. Reinstall with `sudo apt-get install --reinstall ./<package.deb>` or `sudo dnf reinstall ./<package.rpm>`.

Remove with `sudo apt-get remove dzdeploy` (or `sudo apt-get purge dzdeploy`) or `sudo dnf remove dzdeploy`. Only package-owned binaries, symlink, public bootstrap script, example and documentation are removed. Operator configuration, SSH state, game data and Windows services remain outside package ownership.

## CI validation

The pinned GoReleaser OSS snapshot builds both package formats for both architectures, retaining the original ZIPs. CI verifies all asset checksums, package dependencies, architecture metadata, executable formats, an exact payload allowlist, absence of lifecycle hooks, and byte equality with the release's client and companion builds.

Native amd64 and arm64 runners install, reinstall, and remove the matching packages inside Debian 12, Ubuntu 24.04, and AlmaLinux 9 containers. Only container image preparation uses a network. Package transactions, client smoke checks, and isolated `--repo` checks run with container networking disabled. The configuration validator is a local test stub for the latter check; no live deployment or host acceptance is claimed.
