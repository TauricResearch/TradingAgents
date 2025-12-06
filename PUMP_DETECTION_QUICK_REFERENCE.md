# Pump Detection Quick Reference

## 🚀 What's a Pump?
Rapid price increase driven by volume spike, momentum, social buzz, or technical setup. Goal: Enter BEFORE the move, not after.

## 📊 Detection Methods (5-in-1)

| Signal | Threshold | Weight | What It Means |
|--------|-----------|--------|--------------|
| **Volume Spike** | 2x+ average | 25% | Massive interest surge |
| **Price Acceleration** | 5%+ recent | 20% | Momentum building |
| **Social Buzz** | Top trending | 15% | Retail FOMO starting |
| **Oversold Bounce** | RSI < 30 | 20% | Bounce potential high |
| **Catalyst Event** | Within 3mo | 20% | Event-driven pump |

## 🎯 Score = Action

| Score | Signal | Action |
|-------|--------|--------|
| 70+ | 🔴 VERY HIGH | BUY - Strong entry |
| 50-69 | 🟠 HIGH | BUY - Risk mgmt |
| 30-49 | 🟡 MODERATE | WAIT - Need confirmation |
| <30 | 🟢 LOW | SKIP - No signals |

## 💰 Position Management

```
Position Size:  1-2% max per trade
Stop Loss:      2-3% below entry (HARD STOP)
Target 1:       5% profit → Move stop to +2%
Target 2:       10% profit → Reduce to 50%
Target 3:       15%+ profit → Let winners run
```

## ⚠️ Critical Rules (DO THIS)

✅ Always set stop loss at entry  
✅ Use small position sizes (1-2%)  
✅ Exit on volume collapse  
✅ Trail stops as profit grows  
✅ Keep pump trades separate (max 5-10% portfolio)  

## 🚫 Never Do This

❌ Chase after 50%+ gains  
❌ Trade without stop loss  
❌ All-in on pump trades  
❌ Hold overnight (dump at open)  
❌ Ignore volume decline  
❌ Use margin on pumps  
❌ Fight the momentum  

## 🛠️ Quick Commands

```bash
# Demo analysis (cached data)
python pump_detection_demo.py

# Analyze one stock
python pump_screening.py --ticker NVDA

# Analyze on specific date
python pump_screening.py --ticker TSLA --date 2025-12-05

# Full market screening
python pump_screening.py
```

## 🎓 Pump Lifecycle

```
1. Oversold (RSI < 30) or Beaten Down
    ↓
2. Volume Spike (2x+ average)
    ↓
3. Price Acceleration (5-10% in 1-3 days)
    ↓
4. Social Buzz Builds (Reddit, Twitter)
    ↓
5. Peak Euphoria (80-100% move)
    ↓
6. Exhaustion (volume drops)
    ↓
7. Crash (50%+ loss in hours)
```

**BEST ENTRY**: Between steps 1-3  
**WORST ENTRY**: Steps 5-6 (too late!)  
**BEST EXIT**: Step 4-5 (take profits before crash)

## 🚨 Pump-and-Dump Red Flags

These are DANGEROUS - AVOID:
- Penny stock (< $5)
- Extreme volume (10x+)
- Coordinated social hype
- Insider selling at peak
- No fundamental reason
- Stock already up 100%+

## 📈 Real Example

**Date**: Dec 5, 2025  
**Stock**: NVDA  

```
Volume: 3.2x average ✅
Price: +12% this week ✅
Social: #1 trending ✅
RSI: 65 (not oversold) ❌
Earnings: Next week ✅

SCORE: 78/100 = BUY SIGNAL

Entry: $950
Stop: $926 (2.5%)
Target 1: $997 (5%)
Target 2: $1045 (10%)
Target 3: $1100+ (15%+)
```

## 💡 Pro Tips

1. **Early volume matters most** - First 30min spike is key indicator
2. **Social buzz = retail pump** - Instagram/TikTok = next wave
3. **Oversold bounces work best** - RSI < 20 = strong setup
4. **Catalysts amplify moves** - Earnings = bigger pump
5. **Profit in first 5-10%** - Most gains happen there
6. **Volume confirmation = stay** - Fading volume = exit
7. **Scalp multiple times** - Take 2-3% gains repeatedly
8. **Time decay** - Pumps usually done in 1-3 days

## 📋 Pre-Entry Checklist

Before entering ANY pump trade:

- [ ] Pump score ≥ 50?
- [ ] Volume spike confirmed?
- [ ] Stop loss set (2-3%)?
- [ ] Position size ≤ 2%?
- [ ] Total pump allocation ≤ 10%?
- [ ] No overnight holds planned?
- [ ] Exit plan written down?
- [ ] Ready to monitor 24/7?

## 🔗 Related Tools

- `detect_volume_spike()` - Find volume surge
- `detect_price_acceleration()` - Find momentum
- `detect_social_sentiment_surge()` - Find buzz
- `detect_oversold_bounce()` - Find setup
- `detect_catalyst_event()` - Find catalysts
- `calculate_pump_score()` - Get final score

## 📞 When to Skip

- Stock halted by SEC
- Volume is only <1.5x
- No catalyst visible
- Been pumping for 5+ days
- Already up 200%+
- Can't set stop loss
- Feel "FOMO" (Sell signal!)

---

**Remember**: Discipline beats emotion. Stick to rules. Pump trading is HIGH RISK. Size appropriately.
