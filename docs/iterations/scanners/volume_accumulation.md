# Volume Accumulation Scanner

## Current Understanding
Detects stocks with volume >2x average. Key weakness: cannot distinguish buying from
selling — high volume on a down day is distribution, not accumulation. Multi-day mode
(3 of last 5 days >1.5x) is more reliable than single-day spikes. Price-change filter
(<3% absolute move) isolates quiet accumulation from momentum chasing.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Does adding a price-direction filter (volume + flat/up price) improve hit rate?
- [ ] Is 3-of-5-day accumulation a stronger signal than single-day 2x volume?
