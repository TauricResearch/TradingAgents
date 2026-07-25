---
name: tam-adj-peg
description: Test growth claims against market runway, execution quality, and valuation sensitivity.
roles:
  - bull_researcher
  - bear_researcher
triggers:
  - TAM, growth durability, or PEG-style arguments are used
  - valuation depends on execution quality
output_schema:
  - market_runway
  - execution_quality
  - valuation_sensitivity
  - falsifier
---

Treat total addressable market as a constraint, not an automatically reachable
revenue pool. Connect any runway claim to share, capacity, competition, unit
economics, and capital requirements. Explain how execution quality changes the
interpretation of growth and valuation multiples.

If credible TAM or earnings inputs are unavailable, use qualitative ranges and
label the limitation. A PEG-style ratio is not comparable across businesses with
different accounting quality, cyclicality, or capital intensity.
