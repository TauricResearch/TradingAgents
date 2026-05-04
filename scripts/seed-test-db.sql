-- seed-test-portfolio.sql
-- Rich E2E test data for TradingAgents test environment.
-- All positions are on 'test' platform (matches hledger SSOT).
-- AI artefacts (signals, analyses, watchlist) include test platform + synthetic others.

BEGIN TRANSACTION;

-- ── Positions (test platform only) ────────────────────────────────────────────

INSERT INTO positions (ticker, exchange, platform, quantity, avg_cost, entry_date, thesis, status, notes, created_at, updated_at)
VALUES
  ('AAPL',   'US',    'test', 10,   192.00, '2026-04-12', 'AI integration driving services growth',                  'open', 'Test position — WWDC catalyst watch', datetime('now'), datetime('now')),
  ('ETH',    'CRYPTO','test', 0.5, 2850.00, '2026-04-19', 'Crypto exposure test — ETH staking yield 3.8%',          'open', 'Risk-off behaviour expected. Small position.', datetime('now'), datetime('now')),
  ('TSLA',   'US',    'test', 5,    245.00, '2026-04-26', 'EV market share pressure; FSD licensing optionality',   'open', 'Recent addition — watch for thesis invalidation', datetime('now'), datetime('now')),
  ('VWCE.DE', 'XETRA', 'test', 10,  132.00, '2026-04-10', 'All-world ETF — low-cost core holding, accumulating',   'open', 'Accumulating quarterly. MSCI World exposure.', datetime('now'), datetime('now'));

-- ── Signals (test platform — for workflow correlation) ─────────────────────────
-- Dates spread over last 30 days to show timeline in signals view.

INSERT INTO signals (ticker, platform, date, signal, reasoning, confidence, created_at)
VALUES
  -- AAPL signals (mixed — some profitable, some not)
  ('AAPL', 'test', '2026-04-01', 'buy',       'Services segment compounding; Vision Pro ecosystem building', 0.82, datetime('now')),
  ('AAPL', 'test', '2026-04-15', 'hold',      'Services growth strong but stock at fair value', 0.65, datetime('now')),
  ('AAPL', 'test', '2026-04-28', 'underweight','Consumer spending headwinds; hardware cycle peak', 0.58, datetime('now')),
  -- ETH signals
  ('ETH', 'test', '2026-04-10', 'buy',        'On-chain metrics improving; staking yield attractive', 0.71, datetime('now')),
  ('ETH', 'test', '2026-04-25', 'sell',       'Regulatory uncertainty; risk-off macro environment', 0.63, datetime('now')),
  -- TSLA signals
  ('TSLA', 'test', '2026-04-20', 'buy',       'EV market share growth; FSD licensing potential', 0.76, datetime('now')),
  ('TSLA', 'test', '2026-05-01', 'hold',      'Valuation stretched; wait for pullback', 0.60, datetime('now')),
  -- VWCE.DE signals (ETF — more conservative signals)
  ('VWCE.DE', 'test', '2026-04-05', 'buy',    'Global equity exposure; low-cost accumulating', 0.85, datetime('now')),
  ('VWCE.DE', 'test', '2026-04-20', 'overweight', 'Market rotation into broad indices', 0.70, datetime('now')),
  -- Some non-test signals (synthetic AI artefact data — platform not in hledger)
  ('NVDA', 'degiero', '2026-04-08', 'buy',    'Data center GPU demand exceeds supply', 0.88, datetime('now')),
  ('NVDA', 'ibkr',    '2026-04-12', 'overweight', 'AI infrastructure supercycle', 0.85, datetime('now')),
  ('MSFT', 'degiero', '2026-04-10', 'hold',   'Azure AI monetization accelerating', 0.72, datetime('now'));

-- ── Analyses (test platform + one from degiero for feedback correlation) ───────

INSERT INTO analyses (ticker, platform, date, config, raw_state, decision, created_at)
VALUES
  ('AAPL', 'test', '2026-04-01',
   '{"model":"deepseek","risk_tolerance":"medium"}',
   '{"analyst_report":"Services revenue +15% YoY. AI integration expanding margin.","sentiment":"bullish","risk":"medium"}',
   'buy',
   datetime('now')),
  ('ETH', 'test', '2026-04-10',
   '{"model":"deepseek","risk_tolerance":"high"}',
   '{"analyst_report":"On-chain metrics improving. Staking yield 3.8% attractive.","sentiment":"bullish","risk":"high"}',
   'buy',
   datetime('now')),
  ('TSLA', 'test', '2026-04-20',
   '{"model":"deepseek","risk_tolerance":"low"}',
   '{"analyst_report":"FSD licensing optionality underappreciated. EV market share growing.","sentiment":"bullish","risk":"medium"}',
   'buy',
   datetime('now')),
  ('VWCE.DE', 'test', '2026-04-05',
   '{"model":"deepseek","risk_tolerance":"low"}',
   '{"analyst_report":"Broad equity exposure via MSCI World. TER 0.20%. accumulating.","sentiment":"bullish","risk":"low"}',
   'buy',
   datetime('now')),
  -- Degiero analysis (for feedback correlation test)
  ('NVDA', 'degiero', '2026-04-08',
   '{"model":"deepseek","risk_tolerance":"medium"}',
   '{"analyst_report":"GPU supply constrained; data center demand insatiable.","sentiment":"very bullish","risk":"medium"}',
   'buy',
   datetime('now'));

-- ── Watchlist ─────────────────────────────────────────────────────────────────

INSERT INTO watchlist (ticker, platform, exchange, thesis, priority, stage, added_date, last_signal, created_at)
VALUES
  ('META',    'test', 'US',    'Reality Labs approaching profitability; ad revenue accelerating', 'high',   'analyzed',   '2026-04-01', 'overweight', datetime('now')),
  ('GOOGL',   'test', 'US',    'Gemini AI integration across Search and Cloud', 'high', 'candidate', '2026-04-05', 'buy', datetime('now')),
  ('AMZN',    'test', 'US',    'AWS AI services; advertising growth secular', 'medium', 'researching', '2026-04-10', NULL, datetime('now')),
  ('ARM',     'test', 'US',    'Arm IP licensing model; AI on-device compute', 'medium', 'researching', '2026-04-15', NULL, datetime('now')),
  ('BTC',     'test', 'CRYPTO','Macro hedge; institutional adoption accelerating', 'low', 'researching', '2026-04-20', 'hold', datetime('now')),
  ('SOL',     'test', 'CRYPTO','Ethereum L2 competitor; low-cost DeFi ecosystem', 'low', 'researching', '2026-04-22', NULL, datetime('now'));

-- ── Prospects (for prospects view E2E) ────────────────────────────────────────

INSERT INTO watchlist (ticker, platform, exchange, thesis, priority, stage, added_date, last_signal, created_at)
VALUES
  ('ASML',    'test', 'US',    'EUV lithography monopoly; AI chip capex beneficiary', 'high', 'approved', '2026-03-15', 'buy', datetime('now')),
  ('SAP',     'test', 'XETRA', 'ERP migration to cloud; AI copilot for enterprise', 'medium', 'candidate', '2026-03-20', 'hold', datetime('now')),
  ('TKA.DE',  'test', 'XETRA', 'German automation; KONE partnership expected Q3', 'high', 'analyzed', '2026-03-25', 'buy', datetime('now'));

COMMIT;