#!/usr/bin/env bash
set -euo pipefail

C4InterFlow.Cli draw-diagrams \
  --aac-input-paths "./Architecture" \
  --aac-reader-strategy "C4InterFlow.Automation.Readers.YamlAaCReaderStrategy,C4InterFlow.Automation" \
  --interfaces "TradingAgentsFlintShadow.SoftwareSystems.*.Containers.*.Components.*.Interfaces.*" \
  --interfaces "TradingAgentsFlintShadow.SoftwareSystems.*.Containers.*.Interfaces.*" \
  --types c4 c4-static c4-sequence sequence \
  --levels-of-details context container component \
  --formats svg png md \
  --output-dir "./diagrams/tradingagents-flint-shadow"
