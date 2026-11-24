#!/bin/sh
# Copyright 2026 Tauric Research
# SPDX-License-Identifier: Apache-2.0
# Install tradingagents for this machine.
#
#   curl -fsSL https://tauric.ai/tradingagents/install.sh | sh              the latest release
#   curl -fsSL https://tauric.ai/tradingagents/install.sh | sh -s -- 1.2.3  a given release
#
# The latest release is the one GitHub marks latest. The download is checked against the release's
# SHA256SUMS and installed into TRADINGAGENTS_INSTALL_DIR (default ~/.local/bin). It runs as your own user and
# never asks for elevated rights.
#
# TRADINGAGENTS_RELEASE_URL (one release directory with tradingagents-<os>-<arch> and SHA256SUMS) reads the
# release from elsewhere.
set -euf
umask 022

fail() {
	printf 'tradingagents install: %s\n' "$1" >&2
	exit 1
}

releases=https://github.com/TauricResearch/TradingAgents/releases
[ "$#" -le 1 ] || fail "give at most one version"
pin=${1:-}
pin=${pin#v}
release=${TRADINGAGENTS_RELEASE_URL:-}
if [ -n "$pin" ]; then
	printf '%s\n' "$pin" | grep -Eq '^(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})$' ||
		fail "$1 is not a version such as 1.2.3"
	[ -z "$release" ] || fail "a version cannot be given with TRADINGAGENTS_RELEASE_URL"
	release=$releases/download/v$pin
fi
release=${release:-$releases/latest/download}
case $release in
https://* | file://*) ;;
*) fail "the release URL must start with https:// or file://" ;;
esac
release=${release%/}

[ "$(id -u)" != 0 ] || fail "run this as your own user, not as root"

case $(uname -s) in
Linux) os=linux ;;
Darwin) os=darwin ;;
*) fail "$(uname -s) is not supported" ;;
esac
case $(uname -m) in
x86_64 | amd64) arch=x64 ;;
arm64 | aarch64) arch=arm64 ;;
*) fail "$(uname -m) processors are not supported" ;;
esac
if [ "$os" = linux ] && ldd --version 2>&1 | grep -qi musl; then
	fail "Linux with musl (such as Alpine) is not supported; a glibc system is needed"
fi
name="tradingagents-$os-$arch"

command -v curl >/dev/null 2>&1 || fail "curl is needed"
if command -v sha256sum >/dev/null 2>&1; then
	digest() { sha256sum "$1" | cut -d ' ' -f 1; }
elif command -v shasum >/dev/null 2>&1; then
	digest() { shasum -a 256 "$1" | cut -d ' ' -f 1; }
else
	fail "sha256sum or shasum is needed to check the download"
fi

if [ -n "${TRADINGAGENTS_INSTALL_DIR:-}" ]; then
	dir=$TRADINGAGENTS_INSTALL_DIR
elif [ -n "${HOME:-}" ]; then
	dir=$HOME/.local/bin
else
	fail "HOME is not set; set TRADINGAGENTS_INSTALL_DIR to the directory to install into"
fi
work=$(mktemp -d)
partial="$dir/.tradingagents.$$"
trap 'rm -rf "$work" "$partial"' EXIT
# On a signal, exit so the EXIT trap cleans up.
trap 'exit 130' INT
trap 'exit 143' TERM

# https and local files only, after redirects too; the user's curl configuration is ignored. A third
# argument caps the size.
fetch() {
	curl -q --fail --silent --show-error --location --proto '=https,file' --proto-redir '=https' \
		--connect-timeout 20 --max-time 600 ${3:+--max-filesize "$3"} --output "$2" "$1" ||
		fail "could not download $1"
}

fetch "$release/SHA256SUMS" "$work/SHA256SUMS"
fetch "$release/$name" "$work/$name"

# Exactly one well-formed line for this file.
expected=$(grep -E "^[0-9a-f]{64}  $name\$" "$work/SHA256SUMS" | cut -d ' ' -f 1 || true)
[ -n "$expected" ] || fail "SHA256SUMS has no checksum for $name"
[ "$(printf '%s\n' "$expected" | wc -l | tr -d ' ')" = 1 ] || fail "SHA256SUMS has more than one checksum for $name"
[ "$(digest "$work/$name")" = "$expected" ] || fail "the download of $name does not match its checksum; nothing was installed"

# It must start here before it replaces anything, and goes into place in one step.
mkdir -p "$dir"
cp "$work/$name" "$partial"
chmod 755 "$partial"
version=$("$partial" --version 2>/dev/null) || fail "$name does not start on this system; nothing was installed"
[ -z "$pin" ] || [ "$version" = "$pin" ] || fail "the release for $pin says it is $version; nothing was installed"
mv -f "$partial" "$dir/tradingagents"

printf 'Installed tradingagents %s in %s\n' "$version" "$dir"
case :$PATH: in
*:"$dir":*) ;;
*) printf 'Add it to your PATH: export PATH="%s:$PATH"\n' "$dir" ;;
esac
