#!/usr/bin/env bash
# Create a STABLE self-signed code-signing identity for the dev preview app.
#
# Why: ad-hoc signing (`codesign -s -`) gives the binary a fresh cdhash on every
# rebuild, so the app's code identity changes and macOS re-prompts to access its
# own Keychain items each time. A stable identity keeps the code identity (and
# thus the Keychain item ACLs) constant across rebuilds -> no repeated prompts.
#
# The identity lives in a DEDICATED keychain with a known password, so signing is
# non-interactive and never needs your login-keychain password. Idempotent.
set -euo pipefail

IDENTITY="TradingDesk Dev"
KC_NAME="tradingdesk-codesign.keychain-db"
KC_PASS="tradingdesk-dev"
KC_PATH="$HOME/Library/Keychains/$KC_NAME"

# Self-signed certs are untrusted, so they appear without -v; check accordingly.
if security find-identity -p codesigning 2>/dev/null | grep -q "$IDENTITY"; then
    echo "Identity '$IDENTITY' already present — nothing to do."
    exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/codesign.cnf" <<'CNF'
[req]
distinguished_name = dn
x509_extensions = v3
prompt = no
[dn]
CN = TradingDesk Dev
[v3]
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature
extendedKeyUsage = critical,codeSigning
CNF

openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
    -keyout "$TMP/key.pem" -out "$TMP/cert.pem" -config "$TMP/codesign.cnf" >/dev/null 2>&1
# Export with the SYSTEM LibreSSL: homebrew OpenSSL 3's PKCS#12 MAC is unreadable
# by macOS `security import`. Use a password (empty-password p12 also fails).
/usr/bin/openssl pkcs12 -export -inkey "$TMP/key.pem" -in "$TMP/cert.pem" \
    -name "$IDENTITY" -out "$TMP/identity.p12" -passout "pass:$KC_PASS" >/dev/null 2>&1

[ -f "$KC_PATH" ] || security create-keychain -p "$KC_PASS" "$KC_NAME"
security set-keychain-settings "$KC_NAME"                 # disable auto-lock timeout
security unlock-keychain -p "$KC_PASS" "$KC_NAME"
security import "$TMP/identity.p12" -k "$KC_NAME" -P "$KC_PASS" -T /usr/bin/codesign -A >/dev/null 2>&1
# Known-password partition list so codesign uses the key without prompting.
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KC_PASS" "$KC_NAME" >/dev/null 2>&1

# Add the dedicated keychain to the user search list (preserving existing ones).
EXISTING=$(security list-keychains -d user | sed -E 's/^[[:space:]]*"?//; s/"?[[:space:]]*$//')
if ! printf '%s\n' "$EXISTING" | grep -q "$KC_NAME"; then
    # shellcheck disable=SC2086
    security list-keychains -d user -s "$KC_PATH" $EXISTING
fi

echo "Created code-signing identity '$IDENTITY'."
security find-identity -v -p codesigning | grep "$IDENTITY" || true
