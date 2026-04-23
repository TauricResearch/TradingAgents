## 🐛 The Problem: The "Sentiment-Price Divergence" Blind Spot

Currently, `TradingAgents` derives signals primarily from `SentimentAnalysisAgent` and `NewsDataAgent` using a linear assumption:
* **Positive News/Sentiment → Bullish Signal**
* **Negative News/Sentiment → Bearish Signal**

However, market structures (especially in momentum markets like A-shares or Crypto) are non-linear. This logic fails to capture **"Narrative Exhaustion"** and the **"Consensus Trap"**.

### The "Bug" in Current Logic
1. **The "Consensus Trap" (Sell the News)**: When `News Sentiment` reaches 100 (Peak Consensus), the model treats it as a strong Buy. In reality, this often indicates **Distribution** (Smart Money selling to Retail on good news). The model misses the turning point where "Obsession" becomes a rigid trap.
2. **Static vs. Dynamic Sentiment**: The agents treat sentiment as a static data point. They miss the *evolution* of market psychology: *Event → Obsession Formation → Peak Consensus → Breakdown*. A "Positive" sentiment at the start of a trend means something completely different than a "Positive" sentiment at the top.
3. **Ignoring "Path of Least Resistance"**: As Jesse Livermore noted, prices move in the line of least resistance (determined by Price/Volume), not by headlines. The model often overweights News, leading to false signals when price action contradicts the narrative (e.g., Price drops despite Good News).

---

## 💡 The Proposal: Integrating "Market Psychology" & Divergence Checks

I propose enhancing the `RiskAgent` to act as a **Reality Check** against raw sentiment, incorporating basic market methodology.

### 1. Sentiment Divergence Check (The "Livermore" Logic)
* **Divergence Bearish**: If `News Sentiment` is **High** but `Price Action` is **Bearish**, override the signal to **Strong Sell**.
    * *Why*: This indicates the "Path of Least Resistance" is Down, despite the noise. Smart money is exiting.
* **Divergence Bullish**: If `News Sentiment` is **Low** but `Price Action` is **Bullish**, override to **Strong Buy**.
    * *Why*: Accumulation often happens in fear.

### 2. Obsession Phase Detection (The "Consensus" Logic)
* Introduce a concept of **"Narrative Saturation"**.
* If media coverage is **Uniform** and **Extremely Positive** (e.g., >90% positive), flag this as **High Risk of Reversal**, even if the score is perfect.
* **Actionable Advice**: The system should warn: *"Consensus is peaking. If price fails to break resistance, exit immediately."*

### 3. Priority: Price > News
* **Rule**: News explains *why* the move happened, but Price tells us *what* is happening.
* The model should prioritize the **Path of Least Resistance** (Price/Volume) over the loudest narrative. News should only be used as a *confirmation*, not a primary trigger.

---

## 📉 Impact
By addressing this, `TradingAgents` will move from a "Data Summarizer" to a true "Trading Decision Engine". It will help users avoid **"Bull Traps"** caused by blindly following positive news at market tops and understand that **sentiment is often a contrarian indicator at extremes**.
