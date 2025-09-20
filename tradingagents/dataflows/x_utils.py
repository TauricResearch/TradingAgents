import requests
import os
import re
import numpy as np
from typing import Annotated
from datetime import datetime, timedelta
from textblob import TextBlob
from dotenv import load_dotenv

load_dotenv()

def get_x_stock_sentiment(
    ticker: Annotated[str, "Ticker of a company. e.g. AAPL, TSM"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: int = 3
) -> str:
    """Get X sentiment analysis for stock ticker"""

    try:
        bearer_token = os.getenv('X_BEARER_TOKEN')
        if not bearer_token:
            return f"X Analysis: API credentials not configured"

        headers = {"Authorization": f"Bearer {bearer_token}"}

        query = f"${ticker} -is:retweet lang:en"
        url = "https://api.twitter.com/2/tweets/search/recent"

        params = {
            'query': query,
            'max_results': 100,
            'tweet.fields': 'created_at,public_metrics,author_id'
        }

        response = requests.get(url, headers=headers, params=params)

        if response.status_code != 200:
            return f"X Analysis: API error {response.status_code}"

        data = response.json()

        if not data.get('data'):
            return f"X Analysis: No recent posts found for ${ticker}"

        posts = data['data']

        total_sentiment = 0
        weighted_sentiment = 0
        total_weight = 0
        bullish_count = 0
        bearish_count = 0

        sentiments = []
        weights = []

        for post in posts:
            text = clean_post_text(post['text'])
            sentiment = get_sentiment_score(text)

            if len(text.strip()) < 10:
                continue

            metrics = post.get('public_metrics', {})
            engagement = metrics.get('like_count', 0) + metrics.get('retweet_count', 0)
            weight = max(1, engagement + 1)

            sentiments.append(sentiment)
            weights.append(weight)

            weighted_sentiment += sentiment * weight
            total_weight += weight
            total_sentiment += sentiment

            if sentiment > 0.15:
                bullish_count += 1
            elif sentiment < -0.15:
                bearish_count += 1

        if len(sentiments) < 10:
            return f"X Analysis: Insufficient data (only {len(sentiments)} valid posts)"

        sentiments_array = np.array(sentiments)
        weights_array = np.array(weights)

        avg_sentiment = np.average(sentiments_array, weights=weights_array)
        std_sentiment = np.sqrt(np.average((sentiments_array - avg_sentiment)**2, weights=weights_array))

        confidence = min(len(sentiments) / 50.0, 1.0)

        sentiment_label = "NEUTRAL"
        if avg_sentiment > 0.15 and confidence > 0.3:
            sentiment_label = "BULLISH"
        elif avg_sentiment < -0.15 and confidence > 0.3:
            sentiment_label = "BEARISH"

        trend_strength = abs(bullish_count - bearish_count) / max(len(sentiments), 1)
        trend_direction = ""
        if trend_strength > 0.2:
            if bullish_count > bearish_count:
                trend_direction = " TRENDING_UP"
            else:
                trend_direction = " TRENDING_DOWN"

        return f"X Sentiment: {sentiment_label}{trend_direction} (Score: {avg_sentiment:.3f}±{std_sentiment:.3f}, Confidence: {confidence:.2f}, Posts: {len(sentiments)}, Bullish: {bullish_count}, Bearish: {bearish_count})"

    except Exception as e:
        return f"X Analysis: Error - {str(e)[:50]}"

def clean_post_text(text: str) -> str:
    """Clean X post text for sentiment analysis"""
    text = re.sub(r'http\S+|www\S+|https\S+', '', text, flags=re.MULTILINE)
    text = re.sub(r'@\w+|#\w+', '', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    return text.strip()

def get_sentiment_score(text: str) -> float:
    """Get sentiment polarity score using TextBlob"""
    if not text or len(text.strip()) < 3:
        return 0.0

    try:
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity
        return max(-1.0, min(1.0, polarity))
    except (ValueError, TypeError, AttributeError) as e:
        return 0.0