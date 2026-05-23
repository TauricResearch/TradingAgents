# Traders of the Round Table - Castle UI Pack

Drop-in front-end pack that transforms the TradingAgents "Bazaar" view
into the castle-themed "Round Table" experience.

## Files
- castle.css            - full castle theme + scene + carousel + modal styles
- castle-portraits.svg  - 8 inline SVG character portraits + castle crest
- castle-council.js     - scene builder, debate playback engine, live SSE wiring
- README.md             - this file

## Install
1. Copy this folder into your app (e.g. the-bazaar/assets/round-table/).
2. In your index.html, just before </body>, AFTER the React app <script>:

   <link rel="stylesheet" href="assets/round-table/castle.css">
   <script defer src="assets/round-table/castle-council.js"></script>

3. (Optional) Add Cinzel font in <head>:

   <link rel="preconnect" href="https://fonts.googleapis.com">
   <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
   <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700;900&display=swap" rel="stylesheet">

The script auto-mounts on DOMContentLoaded, hides the original Bazaar
verdict and report cards, and renders the council scene + carousel in
their place. It expects the React app to expose window.AGENTS and
that report bodies live in #root .detail-section with <h4> headings
and .detail-content bodies.

## Live mode (drive seats from real SSE)
- fetch wrapper detects /analyze POSTs and flips the IDLE pill to LIVE.
- EventSource wrapper routes SSE events to seats (thinking/speaking/done).
- Edit AGENT_TO_SEAT and the regex matchers at the top of castle-council.js
  if your backend uses different event names.

## Customisation
- Palette: edit :root in castle.css.
- Characters: edit <symbol> ids in castle-portraits.svg.
- Demo script: edit SCRIPT[] near the top of castle-council.js.

## Remove
Delete the two HTML tags. Nothing was written to disk.
