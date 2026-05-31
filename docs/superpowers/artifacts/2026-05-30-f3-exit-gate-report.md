# F3 Exit-Gate Report — 2026-05-30

Window: `2026-05-30T01:38:09+00:00` → `2026-05-31T01:38:09+00:00`

## Auto-criteria

- events ≥ 100: **True** (18024 events)
- auto-promoted watchlist rows ≥ 1: **True** (18)
- no adapter restarts: **True**

## Per-adapter NRestarts

- `iic-sense-gdelt.service`: OK
- `iic-sense-macro.service`: OK
- `iic-sense-polygon.service`: OK
- `iic-sense-rss.service`: OK
- `iic-sense-telegram.service`: OK
- `iic-sense-x.service`: OK
- `iic-triage.service`: OK

## Counts

- total events: 18024
- triaged: 2607
- duplicates: 15417
- duplicates / total: 85.5%

## Dedup spot-check sample (30 rows)

### sample 1
- duplicate: `e79d6e159ff240b0b40c4255e0282c17` (macro, 2026-05-30T07:25:27.267472+00:00)
- original: `1c5e75ec9c95492c95fad91489c46a3c` (macro, 2026-05-29T23:18:20.684403+00:00)

### sample 2
- duplicate: `0794516ed804411ca3cfc90d65c1927a` (rss, 2026-05-30T13:06:20.986246+00:00)
- original: `6377cd5b53404185b3e9b427a2073c71` (rss, 2026-05-30T13:01:19.138063+00:00)

### sample 3
- duplicate: `f509978c4cc94db990a5a2c63629c1a6` (macro, 2026-05-30T09:55:29.337460+00:00)
- original: `0969400b8d71407086c631edae10341d` (macro, 2026-05-29T23:18:20.683492+00:00)

### sample 4
- duplicate: `66d7ff51e61e4054aed20016cfa58eb3` (gdelt, 2026-05-30T07:46:28.927801+00:00)
- original: `4495d487184e4e73a5fbf262f2587164` (gdelt, 2026-05-30T07:15:44.061476+00:00)

### sample 5
- duplicate: `6cbace43301d4e72846f7f3a9dd6fdd4` (macro, 2026-05-30T07:55:27.651014+00:00)
- original: `46f7fac85a974130a6f82e92ac7f0b16` (macro, 2026-05-29T23:18:20.697227+00:00)

### sample 6
- duplicate: `e9948fa029904db881c28ef7c5e2386c` (gdelt, 2026-05-30T16:23:49.961793+00:00)
- original: `4fa1bdcd30d24bb3a7108502b902f0ff` (gdelt, 2026-05-30T15:53:24.216954+00:00)

### sample 7
- duplicate: `6c9fc53137284a4bbc9682987d35144a` (gdelt, 2026-05-30T05:14:11.954313+00:00)
- original: `4d6f2ff0184f41669896082bcfea0e73` (gdelt, 2026-05-30T02:56:25.417769+00:00)

### sample 8
- duplicate: `838b0f2af8b94ead9c88d30b3ff21d1c` (gdelt, 2026-05-30T09:33:16.889820+00:00)
- original: `d6918c1bde634a06a7435bf2057b5fd0` (gdelt, 2026-05-30T07:15:44.031067+00:00)

### sample 9
- duplicate: `e0583de24f3840818e8646d8ff3890e5` (gdelt, 2026-05-30T11:19:55.156241+00:00)
- original: `940ee1a1aede4889ae2bfdd662c0d7b6` (gdelt, 2026-05-30T09:33:16.821910+00:00)

### sample 10
- duplicate: `ead721d8fb944dee9fedcb8e7cafdfbb` (gdelt, 2026-05-30T18:56:36.628487+00:00)
- original: `4399deff628844ef95f44a05d2d2e1ff` (gdelt, 2026-05-30T16:23:49.848289+00:00)

### sample 11
- duplicate: `aac0a91633984990bcb89b4894d5f9d1` (rss, 2026-05-30T01:40:29.991384+00:00)
- original: `e33a9b3a0562459b9c0a57f3e61b239b` (rss, 2026-05-29T23:59:31.503586+00:00)

### sample 12
- duplicate: `bafb0234fe544f749889410dd689a84c` (gdelt, 2026-05-30T21:59:09.597457+00:00)
- original: `bff0395ff6074071a2bf6db739973dbb` (rss, 2026-05-30T16:58:34.429351+00:00)

### sample 13
- duplicate: `79e4be98157646ffa3252b4e54130398` (rss, 2026-05-30T01:55:35.873146+00:00)
- original: `659204b7cc564544a2e63b36c8e661f2` (rss, 2026-05-29T23:14:20.112630+00:00)

### sample 14
- duplicate: `33201a64b2554056b86b2fc33db00aaf` (gdelt, 2026-05-30T22:29:45.757536+00:00)
- original: `d775169b223441c9b30c1c84a21f186a` (gdelt, 2026-05-30T18:56:36.473597+00:00)

### sample 15
- duplicate: `ccf1e2526b674ea789c016bdef65a0b7` (gdelt, 2026-05-30T13:06:25.726021+00:00)
- original: `c267041532604651805c733830b211a6` (gdelt, 2026-05-30T12:20:37.436375+00:00)

### sample 16
- duplicate: `38a4d617beed48438872847a08f15957` (macro, 2026-05-30T23:26:05.529421+00:00)
- original: `575d3efc27b0493095c674cae736f4ae` (macro, 2026-05-29T23:18:20.690172+00:00)

### sample 17
- duplicate: `b07f390ea17e43b0a94974f91470f2a0` (macro, 2026-05-30T04:25:24.620191+00:00)
- original: `83715dca3a754e249bd26f4839637b6b` (macro, 2026-05-29T23:18:20.724856+00:00)

### sample 18
- duplicate: `d88116729bf0461ea815a3f14bbc857e` (rss, 2026-05-30T18:39:35.078951+00:00)
- original: `e22c97cdeaa945a5ad22ed5f9a00d5c1` (rss, 2026-05-30T18:19:22.065323+00:00)

### sample 19
- duplicate: `75e3405d81b34e5fad1d8d3c7f3e0af5` (macro, 2026-05-30T17:55:57.733672+00:00)
- original: `503d4f75505d43198a6e0c870c3234eb` (macro, 2026-05-29T23:18:20.670546+00:00)

### sample 20
- duplicate: `f9847e4cd5fb48808e1ed247f54c2794` (gdelt, 2026-05-30T14:22:21.839125+00:00)
- original: `ba373bd5fab8441db9ba05d3935ccd60` (gdelt, 2026-05-30T13:36:54.953197+00:00)

### sample 21
- duplicate: `7e9e227ccb194edb83f7d0772e987518` (gdelt, 2026-05-30T16:23:50.025675+00:00)
- original: `aa8469844cf24e3facb2a66057979958` (gdelt, 2026-05-30T14:22:21.773890+00:00)

### sample 22
- duplicate: `40ae0fe2af904f298f996f1f0dfa9067` (macro, 2026-05-30T16:25:55.936078+00:00)
- original: `942abb68ad7544b5aa310173dcd272e6` (macro, 2026-05-29T23:18:20.645378+00:00)

### sample 23
- duplicate: `e9554375edcd4f5682495d615bccfe56` (gdelt, 2026-05-30T11:35:11.397771+00:00)
- original: `cd11220fc7ea4c29a7814d77a0ea71cf` (gdelt, 2026-05-30T10:03:38.555134+00:00)

### sample 24
- duplicate: `15d6c2eeccf14366ac6e4d4e75070fe0` (macro, 2026-05-30T11:55:30.911692+00:00)
- original: `9c7e96b15ce54f3ebbd0081d7ee451a4` (macro, 2026-05-29T23:18:20.641510+00:00)

### sample 25
- duplicate: `17044ff9acd747e2a44e2c2a09f16c13` (gdelt, 2026-05-30T12:20:37.582649+00:00)
- original: `32bb6aa472bb4461b18c14b6dabe97a2` (gdelt, 2026-05-30T11:19:55.011970+00:00)

### sample 26
- duplicate: `2790bf064eaf40569e02582b0811d594` (rss, 2026-05-31T01:18:31.679046+00:00)
- original: `5007823b983c4b0d9d0d95744cf3d201` (rss, 2026-05-30T23:42:38.020504+00:00)

### sample 27
- duplicate: `2423759450fc4781b4158c34dd08c85e` (macro, 2026-05-30T04:25:24.550184+00:00)
- original: `0fd0119eca44444fb2f8b764545c360d` (macro, 2026-05-29T23:18:20.651954+00:00)

### sample 28
- duplicate: `23e54dc9434540389bee658477ddde28` (gdelt, 2026-05-30T06:30:11.466918+00:00)
- original: `3a326ae02c7f42d799b0302ebdb37e48` (gdelt, 2026-05-30T06:14:53.526649+00:00)

### sample 29
- duplicate: `8a310e5610f74fb9b1bcfcdca8deccc5` (gdelt, 2026-05-30T19:26:59.670749+00:00)
- original: `514ac337b9b8418c8690dc7eefe69b5b` (rss, 2026-05-30T16:58:34.413203+00:00)

### sample 30
- duplicate: `488154239bd943efa9bc3b3cf3b180b6` (rss, 2026-05-30T02:00:39.602000+00:00)
- original: `22435824d03b4ce4a4a0d05e9848346e` (rss, 2026-05-29T23:14:21.872423+00:00)

## Sign-off

Spot-check pass (≥24/30 are genuine duplicates): **YES** — Adversarial content audit of 37 stratified dup/original pairs (15 cross-source + 8 gdelt + 8 rss + 6 macro), reading both raw event JSONs for each: **35 genuine, 0 false-positive, 2 unverifiable** (empty `raw_path`). Genuine rate 94.6% (100% of the verifiable pairs), well past ≥24/30. The 85.5% duplicate fraction is legitimate re-poll/syndication overlap — gdelt 15-min polls + mirror-domain wire syndication, rss feed re-polls, macro release re-emit — **not** over-merging: no two distinct stories were collapsed, and all 552 cross-source dups are gdelt re-crawls of the kept RSS item. Reviewer: automated adversarial audit, 2026-05-31.

Overall auto-pass: **True**

## Reviewer addendum — source-health findings (do not affect gate pass)

The gate passed on gdelt + rss volume, but the per-source audit surfaced two real
issues worth tracking:

- **macro (HIGH, fixed):** off-by-one cursor-persistence bug re-emitted ~all FRED
  releases every poll (3,525 duplicates, 0 net-new signal in-window). Root cause:
  `EnvelopeWriter.write` persists the cursor per-XADD and releases iterate DESC, so
  the smallest emitted id won. Fixed in `macro.py` (persist `new_max` once after the
  loop) + regression test.
- **telegram (MEDIUM, deferred):** only 6 events/24h — cointelegraph delivered 0 and
  WatcherGuru 1, despite a healthy connection (no disconnects/FloodWait). Points to a
  channel-resolution/subscription gap (`NewMessage(chats=…)` silently drops unresolved
  usernames). Fix deferred: add explicit `get_entity` resolution + per-channel
  `resolved → id, joined=bool` startup logging so dark channels are visible.

All 18 auto-promotions verified legitimate (real, active tickers; trigger texts name
the ticker; promotions sourced only from triaged events).