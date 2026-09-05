# PR26: A-Share Game Research Universe

PR26 introduces the first industry-specific research layer for two seed A-share
companies:

- `002624` Perfect World;
- `002602` Century Huatong.

The implementation is a reusable entity and product model. Adding another game
company does not require changing cockpit behavior or creating stock-specific
branches in the workflow.

## Coverage

Each company snapshot separates:

- the listed company and material game operating entities;
- live, legacy-live, and pipeline products;
- product aliases, genres, platforms, and markets;
- launch, overseas-launch, live-operations, and pipeline catalysts;
- official evidence with availability dates and source URLs.

Facts have an explicit `known_as_of` date. A historical snapshot excludes an
entity, product, catalyst, or source which had not yet been disclosed by the
requested date.

## Cockpit

The local cockpit now exposes three game-industry panels:

- **Game Business**: research focus and entity relationships;
- **Game Product Matrix**: title lifecycle, genre, platform, and market;
- **Game Catalyst Tracker**: dated and ongoing product events.

`GET /api/game-universe` returns every covered company. The regular snapshot API
includes one `game_research` object, and `/api/symbols` includes both seed
symbols even before market artifacts have been cached.

## Evidence policy

The seed records use official company releases, official product sites, and a
Shenzhen Stock Exchange filing. This catalog is a current research aid rather
than an immutable run artifact, so archived Markdown reports are not modified by
later catalog updates.

The next slice should ingest National Press and Publication Administration game
approval results as dated artifacts, then link approved operators to this entity
graph with explicit mapping confidence and manual review for ambiguous names.
