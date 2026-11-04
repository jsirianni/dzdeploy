#!/usr/bin/env bash
# Runs only in a disposable, network-disabled package-test container.
set -euo pipefail
format=$1
case $(uname -m) in x86_64) native=amd64 ;; aarch64) native=arm64 ;; *) exit 1 ;; esac
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
native_package=
for package in /packages/*."$format"; do
    extract="$scratch/extract"
    mkdir -p "$extract"
    if [[ $format == deb ]]; then
        [[ $(dpkg-deb -f "$package" Package) == dzdeploy ]]
        arch=$(dpkg-deb -f "$package" Architecture)
        depends=$(dpkg-deb -f "$package" Depends)
        dpkg-deb -e "$package" "$scratch/control"
        for hook in preinst postinst prerm postrm; do test ! -e "$scratch/control/$hook"; done
        dpkg-deb -x "$package" "$extract"
        case $arch in amd64|arm64) ;; *) exit 1 ;; esac
    else
        [[ $(rpm -qp --qf '%{NAME}' "$package") == dzdeploy ]]
        arch=$(rpm -qp --qf '%{ARCH}' "$package")
        depends=$(rpm -qp --requires "$package")
        [[ -z $(rpm -qp --scripts "$package") ]]
        [[ $(rpm -qp --qf '[%{FILEUSERNAME}:%{FILEGROUPNAME}\n]' "$package" | sort -u) == root:root ]]
        (cd "$extract"; rpm2cpio "$package" | cpio -idm --quiet)
        case $arch in x86_64) arch=amd64 ;; aarch64) arch=arm64 ;; *) exit 1 ;; esac
    fi
    grep -qw git <<< "$depends"
    grep -qw ca-certificates <<< "$depends"
    ! grep -Eiw 'python[0-9.-]*|golang|go' <<< "$depends"
    real="/usr/lib/dzdeploy/linux_$arch/dzdeploy"
    [[ $(readlink "$extract/usr/bin/dzdeploy") == "$real" ]]
    cmp "$extract$real" "/packages/linux_$arch/dzdeploy"
    cmp "$extract$(dirname "$real")/agents/windows-amd64/dzdeploy.exe" /packages/windows_amd64/dzdeploy.exe
    file "$extract$(dirname "$real")/agents/windows-amd64/dzdeploy.exe" | grep -q 'PE32+.*x86-64'
    case $arch in amd64) machine='Advanced Micro Devices X86-64' ;; arm64) machine=AArch64 ;; esac
    readelf -h "$extract$real" | grep -q "$machine"
    test -x "$extract$real"
    # Exact payload allowlist rules out configuration, secrets, units and hooks.
    diff -u <(printf '%s\n' "usr/lib/dzdeploy/linux_$arch/dzdeploy" "usr/lib/dzdeploy/linux_$arch/agents/windows-amd64/dzdeploy.exe" usr/share/dzdeploy/bootstrap-windows.ps1 usr/share/doc/dzdeploy/deploy.example.yaml usr/share/doc/dzdeploy/deployment.md usr/share/doc/dzdeploy/operator-workflows.md | sort) <(cd "$extract"; find usr -type f | sort)
    [[ $(find "$extract" -type l | wc -l) == 1 ]]
    [[ $arch != "$native" ]] || native_package=$package
    rm -rf -- "$extract" "$scratch/control"
    echo "$format/$arch: metadata, architecture, payload and companion verified"
done
[[ -n $native_package ]]

operator="$scratch/operator"
mkdir -p "$operator/.deploy" "$operator/.ssh" /etc/dzdeploy
printf 'operator config\n' > "$operator/deploy.yaml"
printf 'private state\n' > "$operator/.deploy/state"
printf 'private key\n' > "$operator/.ssh/key"
printf 'operator managed\n' > /etc/dzdeploy/keep
(cd "$operator"; sha256sum deploy.yaml .deploy/state .ssh/key) > "$scratch/operator-checksums"
check_preserved() {
    (cd "$operator"; sha256sum --check "$scratch/operator-checksums")
    grep -qx 'operator managed' /etc/dzdeploy/keep
}
check_installed() {
    [[ $(command -v dzdeploy) == /usr/bin/dzdeploy ]]
    [[ $(readlink -f /usr/bin/dzdeploy) == "/usr/lib/dzdeploy/linux_$native/dzdeploy" ]]
    [[ $(stat -c '%U:%G' "$(readlink -f /usr/bin/dzdeploy)") == root:root ]]
    dzdeploy --help
    dzdeploy version
    cmp "/usr/lib/dzdeploy/linux_$native/agents/windows-amd64/dzdeploy.exe" /packages/windows_amd64/dzdeploy.exe
    # Prove --repo uses operator configuration, independently of install path.
    mkdir -p "$operator/.tools/dzcli"
    printf '#!/bin/sh\nprintf "fixture validator: %%s\\n" "$*"\n' > "$operator/.tools/dzcli/dzcli"
    chmod +x "$operator/.tools/dzcli/dzcli"
    for folder in first-light-badlands-nasdara-us-east first-light-badlands-nasdara-staging-us-east first-light-deer-isle-expansion-us-east1; do
        mkdir -p "$operator/servers/current/$folder"
        printf '// fixture\n' > "$operator/servers/current/$folder/serverDZ.cfg"
    done
    dzdeploy validate all --offline --repo "$operator" --json > "$scratch/validation.json"
    grep -q 'fixture validator: validate server' "$scratch/validation.json"
    grep -q '"failures": 0' "$scratch/validation.json"
    check_preserved
}
if [[ $format == deb ]]; then
    dpkg -i "$native_package"
    dpkg-query -S /usr/bin/dzdeploy
    check_installed
    dpkg -i "$native_package" # Reinstall through the package manager's upgrade path.
    check_installed
    dpkg -r dzdeploy
    check_preserved
    dpkg -i "$native_package"
    dpkg --purge dzdeploy
else
    rpm -i "$native_package"
    rpm -qf /usr/bin/dzdeploy
    check_installed
    rpm -U --replacepkgs "$native_package"
    check_installed
    rpm -e dzdeploy
fi
! command -v dzdeploy
test ! -e "/usr/lib/dzdeploy/linux_$native/dzdeploy"
test ! -e "/usr/lib/dzdeploy/linux_$native/agents/windows-amd64/dzdeploy.exe"
check_preserved
echo "$format/$native: installation, reinstallation and removal passed without network or host access"
