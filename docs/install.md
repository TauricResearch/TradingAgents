# Install

TradingAgents is one executable file. Builds are published for Linux (x64 and arm64, glibc) and macOS (Intel and Apple silicon).

## With the installer

```bash
curl -fsSL https://tauric.ai/tradingagents/install.sh | sh
```

It installs the latest release for your machine into `~/.local/bin` (or `TRADINGAGENTS_INSTALL_DIR`), after checking it against the release's `SHA256SUMS`. To install a particular release, name its version: `curl -fsSL https://tauric.ai/tradingagents/install.sh | sh -s -- 1.2.3`. It runs as your own user and never asks for elevated rights.

## With npm

```bash
npm i -g @tauric/tradingagents
```

It installs the executable for your machine as a package of its own; update it the same way.

## From a release

Download the file for your machine (`tradingagents-linux-x64`, `tradingagents-linux-arm64`, `tradingagents-darwin-x64` or `tradingagents-darwin-arm64`) and `SHA256SUMS` from the [releases page](https://github.com/TauricResearch/TradingAgents/releases), check it, and put it on your `PATH`:

```bash
sha256sum --check --ignore-missing SHA256SUMS      # on macOS: shasum -a 256 --check --ignore-missing SHA256SUMS
mkdir -p ~/.local/bin
chmod +x tradingagents-linux-x64                   # the file you downloaded
mv tradingagents-linux-x64 ~/.local/bin/tradingagents
```

If `~/.local/bin` is not on your `PATH` yet, add it in your shell's profile.

On macOS, a file downloaded in a browser may have to be allowed the first time: under System Settings > Privacy & Security, or with `xattr -d com.apple.quarantine <file>`.

## Updates

A session in the terminal checks for a newer release at most once a day, in the background. At the next start it asks whether to update now, skip, or skip until a newer release than that one is out; updating runs `tradingagents update` (or npm's command for an npm install), and the new version runs from the following start. A copy installed another way is told what to run instead. The check is a plain request for the latest release: no identifier, and nothing about your questions. `TRADINGAGENTS_NO_UPDATE_CHECK=1` turns it off. Nothing is installed without you asking, and `-p` never asks.

To update, run:

```bash
tradingagents update
```

It downloads the latest release, checks it against `SHA256SUMS`, makes sure it starts, and then puts it in place of the old file in one step. A copy installed by a package manager, or in a folder you cannot write, is left alone, with what to do instead.

After an update, the first session shows what is new once; `/changelog` shows it again.
