# Semantic News Scanner

## Current Understanding
Currently regex-based extraction, not semantic. Headline text is not included in
candidate context — the context just says "Mentioned in recent market news" which
is not informative. Catalyst classification from headline keywords (upgrade/FDA/
acquisition/earnings) would improve LLM scoring quality significantly.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Would embedding-based semantic matching outperform keyword regex?
- [ ] Does catalyst classification (FDA vs earnings vs acquisition) affect hit rate?
