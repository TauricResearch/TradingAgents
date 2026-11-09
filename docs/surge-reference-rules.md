# Reference-card review and implementation mapping

Reviewed locally on 2026-11-08: Reference Cards 1 and 2, version 20260501,
copyright SurgeU LLC, all rights reserved. Each PDF has two pages. The diagrams
contain the substantive rules; text extraction alone misses them. The PDFs and
rendered pages are not bundled with this repository. No redistribution license
for the course materials is inferred from this project's Apache-2.0 license.

## Boundary rules (Card 1, page 1)

The default proximal option uses the base's body edge: highest for demand, lowest
for supply. The card explicitly allows the trader to choose proximal placement.
The distal span differs by pattern:

| Pattern | Distal extremum | Span included |
|---|---|---|
| DBR | Low | Incoming leg, base, departing leg |
| RBR | Low | Base and departing leg |
| RBD | High | Incoming leg, base, departing leg |
| DBD | High | Base and departing leg |

`zone_boundaries` implements these formulas for supplied multi-candle spans. The
detector still uses experimental single-candle incoming/departing legs and
configurable base thresholds. Thus documented boundary math does not certify the
detected formation as an official setup. The boundary version and detection version
are separate. Zone IDs include the boundary version, preventing old/new collisions.

## Score bands (Card 2, page 2)

`score_evidence` applies the six bands to explicit as-of evidence:

- Strength (2): displacement of at least 2:1 plus breakout; both, one, or neither
  award 2, 1, or 0. The detector's trailing BOS flag is not used as a substitute.
- Time (1): 1-3 base candles earn 1; 4-6 earn 0.5; more than 6 earn 0.
- Freshness (2): untested earns 2; a test penetrating at most half the zone earns
  1; a deeper test up to the distal boundary earns 0. Beyond-distal evidence is
  outside this score band's scope and needs lifecycle handling; it remains unscored.
- Trend (2): properly located with-trend, sideways, and against-trend formations
  earn 2, 1, and 0. Controlling-swing and breakout-segment validation is a prerequisite.
- Curve (1): demand low/supply high earns 1; middle earns 0.5; the opposite earns 0.
- Profit Zone (2): reward/risk to an opposing fresh zone earns 2 at 5:1 or greater,
  1 at 3:1 or greater, otherwise 0. Arbitrary target multiples are not this evidence.

Unknown evidence remains null, including unknown breakout state or opposing-zone
freshness. Report earned points and the maximum of evaluated components separately;
never normalize a partial score to 10. Only complete scorecards receive the card's
entry guidance: proximal at 8.5+, confirmation at 7 through below 8.5, no trade below
7. This is plan guidance, never a calibrated success probability or an order.

The dashboard automatically supplies only base count, yielding a **Time-only partial
score**. It does not assume a newly detected zone is fresh without revisit analysis.
The scoring API requires evidence known at its aware as-of timestamp; callers remain
responsible for verifying measurement provenance. It does not establish temporal
integrity simply because evidence has a timestamp.

## Further rules now available, not yet automated

Card 1 page 2 specifies HTF curve, ITF trend, and LTF zones. Its timeframe mapping is:
hourly income 60m/15m/5m; daily income Daily/60m/15m; weekly income Weekly/Daily/240m
or 60m; monthly income Monthly/Weekly/Daily. HTF curve zones use wick-to-wick bounds.
An uptrend demand entry is above the controlling swing low inside a breakout segment;
a downtrend supply entry is below the controlling swing high inside such a segment.

The cards illustrate swings/segments, steep departures and curve locations, but do
not supply an exhaustive machine definition for pivot confirmation, leg extension,
steepness, curve partitions, or breakout acceptance. These need explicit, versioned
implementation conventions and tests, with assumptions labeled. Do not invent numeric
thresholds and call them official. The minimum stop buffer is 2% of daily ATR for
income styles and 10% for wealth styles, rounded up; the rounding/tick convention
and ATR calculation are not fully specified. The decision
matrix and entry execution mechanics also remain a separate increment.

Next: causal revisit/penetration tracking, verified multi-timeframe evidence, opposing
fresh-zone risk/reward, then a full automated score. Keep existing agent workflows
and production order behavior unchanged.
