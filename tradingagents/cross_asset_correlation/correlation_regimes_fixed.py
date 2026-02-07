"""
Correlation Regime Detector
Identifies changing correlation patterns and market regimes.

Detects:
- Correlation breakdowns and regime shifts
- Crisis periods (flight to quality, contagion)
- Bull/bear market correlation patterns
- Seasonal correlation patterns
- Structural breaks in relationships

Based on regime switching models and structural break detection.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import warnings
from scipy import stats
from scipy.signal import find_peaks
from sklearn.cluster import KMeans


class CorrelationRegime(Enum):
    """Correlation regime classifications."""
    NORMAL = "normal"  # Stable, moderate correlations
    CRISIS = "crisis"  # High correlations (contagion)
    DECOUPLING = "decoupling"  # Low/negative correlations
    TRENDING = "trending"  # Strong positive trends
    DIVERGING = "diverging"  # Strong negative trends
    VOLATILE = "volatile"  # High volatility, unstable correlations
    SEASONAL = "seasonal"  # Seasonal pattern


@dataclass
class RegimeDetectionResult:
    """Results of regime detection."""
    regime_type: CorrelationRegime
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    confidence: float
    characteristics: Dict[str, float]
    assets_affected: List[str]


class CorrelationRegimeDetector:
    """Detects and analyzes correlation regimes."""
    
    def __init__(
        self,
        min_regime_length: int = 10,
        detection_method: str = "rolling_volatility"
    ):
        """
        Initialize regime detector.
        
        Args:
            min_regime_length: Minimum length of a regime in periods
            detection_method: Primary detection method
        """
        self.min_regime_length = min_regime_length
        self.detection_method = detection_method
        
    def detect_regimes(
        self,
        correlation_series: pd.Series,
        price_data: Optional[pd.DataFrame] = None,
        methods: List[str] = None
    ) -> List[RegimeDetectionResult]:
        """
        Detect correlation regimes in time series.
        
        Args:
            correlation_series: Time series of correlation values
            price_data: Optional price data for additional context
            methods: List of detection methods to use
            
        Returns:
            List of detected regimes
        """
        if methods is None:
            methods = ["rolling_volatility", "changepoint", "clustering"]
            
        # Validate input
        if len(correlation_series) < self.min_regime_length * 2:
            raise ValueError(
                f"Insufficient data. Need at least {self.min_regime_length * 2} periods"
            )
            
        # Apply each detection method
        all_regimes = []
        
        for method in methods:
            try:
                if method == "rolling_volatility":
                    regimes = self._detect_by_volatility(correlation_series)
                elif method == "changepoint":
                    regimes = self._detect_changepoints(correlation_series)
                elif method == "clustering":
                    regimes = self._detect_by_clustering(correlation_series)
                elif method == "markov":
                    regimes = self._detect_markov_regimes(correlation_series)
                else:
                    warnings.warn(f"Unknown detection method: {method}")
                    continue
                    
                all_regimes.extend(regimes)
                
            except Exception as e:
                warnings.warn(f"Method {method} failed: {e}")
                continue
                
        # Merge overlapping regimes
        merged_regimes = self._merge_regimes(all_regimes)
        
        # Classify regimes
        classified_regimes = []
        for regime in merged_regimes:
            classified = self._classify_regime(regime, correlation_series, price_data)
            classified_regimes.append(classified)
            
        return classified_regimes
    
    def analyze_regime_transitions(
        self,
        regimes: List[RegimeDetectionResult]
    ) -> pd.DataFrame:
        """
        Analyze transitions between regimes.
        
        Args:
            regimes: List of detected regimes
            
        Returns:
            DataFrame with transition probabilities and statistics
        """
        if len(regimes) < 2:
            return pd.DataFrame()
            
        # Create transition matrix
        regime_types = [r.regime_type for r in regimes]
        unique_regimes = list(set(regime_types))
        
        # Initialize transition matrix
        transition_matrix = pd.DataFrame(
            0,
            index=unique_regimes,
            columns=unique_regimes
        )
        
        # Count transitions
        for i in range(len(regime_types) - 1):
            from_regime = regime_types[i]
            to_regime = regime_types[i + 1]
            transition_matrix.loc[from_regime, to_regime] += 1
            
        # Convert to probabilities
        row_sums = transition_matrix.sum(axis=1)
        transition_probs = transition_matrix.div(row_sums, axis=0)
        
        # Calculate regime statistics
        regime_stats = []
        for regime_type in unique_regimes:
            regime_instances = [r for r in regimes if r.regime_type == regime_type]
            
            if regime_instances:
                durations = [
                    (r.end_date - r.start_date).days
                    for r in regime_instances
                ]
                
                stats_dict = {
                    'regime_type': regime_type.value,
                    'count': len(regime_instances),
                    'avg_duration_days': np.mean(durations),
                    'std_duration_days': np.std(durations),
                    'min_duration_days': np.min(durations),
                    'max_duration_days': np.max(durations),
                    'total_days': np.sum(durations),
                    'frequency': len(regime_instances) / len(regimes)
                }
                
                regime_stats.append(stats_dict)
                
        return pd.DataFrame(regime_stats), transition_probs
    
    def predict_next_regime(
        self,
        current_regime: CorrelationRegime,
        transition_matrix: pd.DataFrame,
        market_conditions: Optional[Dict] = None
    ) -> Tuple[CorrelationRegime, float]:
        """
        Predict next regime based on transition probabilities.
        
        Args:
            current_regime: Current regime
            transition_matrix: Transition probability matrix
            market_conditions: Optional market condition indicators
            
        Returns:
            Tuple of (predicted regime, probability)
        """
        if current_regime.value not in transition_matrix.index:
            return current_regime, 1.0
            
        # Get transition probabilities from current regime
        probs = transition_matrix.loc[current_regime.value]
        
        # Adjust based on market conditions if provided
        if market_conditions:
            probs = self._adjust_probs_with_conditions(probs, market_conditions)
            
        # Find most likely next regime
        next_regime = probs.idxmax()
        probability = probs.max()
        
        return CorrelationRegime(next_regime), probability
    
    def detect_crisis_periods(
        self,
        correlation_matrix_series: pd.DataFrame,
        volatility_series: pd.Series,
        threshold: float = 0.8
    ) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
        """
        Detect crisis periods based on correlation and volatility.
        
        Args:
            correlation_matrix_series: Time series of correlation matrices
            volatility_series: Time series of market volatility
            threshold: Correlation threshold for crisis detection
            
        Returns:
            List of (start_date, end_date) tuples for crisis periods
        """
        # Calculate average correlation over time
        avg_correlations = []
        dates = []
        
        for date, corr_matrix in correlation_matrix_series.items():
            # Flatten matrix (excluding diagonal)
            corr_values = corr_matrix.values[
                np.triu_indices_from(corr_matrix, k=1)
            ]
            avg_corr = np.mean(corr_values)
            avg_correlations.append(avg_corr)
            dates.append(date)
            
        avg_corr_series = pd.Series(avg_correlations, index=dates)
        
        # Detect crisis periods (high correlation + high volatility)
        crisis_periods = []
        in_crisis = False
        crisis_start = None
        
        for date in avg_corr_series.index:
            avg_corr = avg_corr_series[date]
            vol = volatility_series.get(date, 0)
            
            is_crisis = (avg_corr >= threshold) and (vol > volatility_series.median())
            
            if is_crisis and not in_crisis:
                # Start of crisis
                in_crisis = True
                crisis_start = date
            elif not is_crisis and in_crisis:
                # End of crisis
                in_crisis = False
                if crisis_start:
                    crisis_periods.append((crisis_start, date))
                    crisis_start = None
                    
        # Handle ongoing crisis at end
        if in_crisis and crisis_start:
            crisis_periods.append((crisis_start, avg_corr_series.index[-1]))
            
        return crisis_periods
    
    def _detect_by_volatility(self, correlation_series: pd.Series) -> List[Dict]:
        """Detect regimes based on rolling volatility."""
        # Calculate rolling volatility
        window = min(20, len(correlation_series) // 4)
        rolling_vol = correlation_series.rolling(window).std()
        
        # Normalize volatility
        vol_normalized = (rolling_vol - rolling_vol.mean()) / rolling_vol.std()
        
        # Detect high/low volatility periods
        regimes = []
        current_regime = None
        regime_start = None
        
        for date, vol in vol_normalized.items():
            if pd.isna(vol):
                continue
                
            if vol > 1.0:
                regime_type = "high_vol"
            elif vol < -1.0:
                regime_type = "low_vol"
            else:
                regime_type = "normal"
                
            if regime_type != current_regime:
                if current_regime is not None and regime_start:
                    regimes.append({
                        'type': current_regime,
                        'start': regime_start,
                        'end': date
                    })
                current_regime = regime_type
                regime_start = date
                
        # Add final regime
        if current_regime is not None and regime_start:
            regimes.append({
                'type': current_regime,
                'start': regime_start,
                'end': correlation_series.index[-1]
            })
            
        return regimes
    
    def _detect_changepoints(self, correlation_series: pd.Series) -> List[Dict]:
        """Detect regimes using changepoint detection."""
        # Clean data
        clean_series = correlation_series.dropna()
        
        if len(clean_series) < 10:
            return []
            
        # Simplified changepoint detection using variance changes
        regimes = []
        window = min(20, len(clean_series) // 5)
        
        # Calculate rolling variance
        rolling_var = clean_series.rolling(window).var()
        
        # Detect significant variance changes
        var_mean = rolling_var.mean()
        var_std = rolling_var.std()
        
        current_regime = None
        regime_start = None
        
        for date, var in rolling_var.items():
            if pd.isna(var):
                continue
                
            if var > var_mean + var_std:
                regime_type = "high_var"
            elif var < var_mean - var_std:
                regime_type = "low_var"
            else:
                regime_type = "normal_var"
                
            if regime_type != current_regime:
                if current_regime is not None and regime_start:
                    regimes.append({
                        'type': current_regime,
                        'start': regime_start,
                        'end': date
                    })
                current_regime = regime_type
                regime_start = date
                
        # Add final regime
        if current_regime is not None and regime_start:
            regimes.append({
                'type': current_regime,
                'start': regime_start,
                'end': clean_series.index[-1]
            })
            
        return regimes
    
    def _detect_by_clustering(self, correlation_series: pd.Series) -> List[Dict]:
        """Detect regimes using clustering."""
        # Prepare features for clustering
        clean_series = correlation_series.dropna()
        
        if len(clean_series) < self.min_regime_length * 3:
            return []
            
        # Create feature matrix (value, rolling mean, rolling std)
        window = min(10, len(clean_series) // 10)
        features = pd.DataFrame({
            'value': clean_series,
            'rolling_mean': clean_series.rolling(window).mean(),
            'rolling_std': clean_series.rolling(window).std()
        }).dropna()
        
        # Determine optimal number of clusters (2-4)
        n_clusters = min(4, max(2, len(features) // (self.min_regime_length * 2)))
        
        # Apply K-means clustering
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        clusters = kmeans.fit_predict(features)
        
        # Convert clusters to regimes
        regimes = []
        current_cluster = None
        regime_start = None
        
        for idx, (date, cluster) in enumerate(zip(features.index, clusters)):
            if cluster != current_cluster:
                if current_cluster is not None and regime_start:
                    regimes.append({
                        'type': f'cluster_{current_cluster}',
                        'start': regime_start,
                        'end': features.index[idx - 1],
                        'cluster': current_cluster,
                        'center': kmeans.cluster_centers_[current_cluster]
                    })
                current_cluster = cluster
                regime_start = date
                
        # Add final regime
        if current_cluster is not None and regime_start:
            regimes.append({
                'type': f'cluster_{current_cluster}',
                'start': regime_start,
                'end': features.index[-1],
                'cluster': current_cluster,
                'center': kmeans.cluster_centers_[current_cluster]
            })
            
        return regimes
    
    def _detect_markov_regimes(self, correlation_series: pd.Series) -> List[Dict]:
        """Detect regimes using Markov switching model (simplified)."""
        # Simplified implementation - in production would use statsmodels
        clean_series = correlation_series.dropna()
        
        if len(clean_series) < 50:
            return []
            
        # Simple threshold-based regime detection
        mean_val = clean_series.mean()
        std_val = clean_series.std()
        
        regimes = []
        current_regime = None
        regime_start = None
        
        for date, value in clean_series.items():
            if value > mean_val + std_val:
                regime_type = "high"
            elif value < mean_val - std_val:
                regime_type = "low"
            else:
                regime_type = "normal"
                
            if regime_type != current_regime:
                if current_regime is not None and regime_start:
                    # Check minimum length
                    if (date - regime_start).days >= self.min_regime_length:
                        regimes.append({
                            'type': regime_type,
                            'start': regime_start,
                            'end': date
                        })
                current_regime = regime_type
                regime_start = date
                
        # Add final regime
        if current_regime is not None and regime_start:
            regimes.append({
                'type': current_regime,
                'start': regime_start,
                'end': clean_series.index[-1]
            })
            
        return regimes
    
    def _merge_regimes(self, regimes: List[Dict]) -> List[Dict]:
        """Merge overlapping regimes."""
        if not regimes:
            return []
            
        # Sort by start date
        regimes.sort(key=lambda x: x['start'])
        
        merged = []
        current = regimes[0]
        
        for regime in regimes[1:]:
            # Check if regimes overlap or are adjacent
            if regime['start'] <= current['end'] or (
                regime['start'] - current['end']).days <= 1:
                # Merge regimes
                current['end'] = max(current['end'], regime['end'])
                # Combine type information
                if 'type' in current and 'type' in regime:
                    current['type'] = f"{current['type']}_{regime['type']}"
            else:
                merged.append(current)
                current = regime
                
        merged.append(current)
        
        return merged
    
    def _classify_regime(
        self,
        regime: Dict,
        correlation_series: pd.Series,
        price_data: Optional[pd.DataFrame] = None
    ) -> RegimeDetectionResult:
        """Classify a regime based on its characteristics."""
        # Extract regime data
        regime_data = correlation_series.loc[regime['start']:regime['end']]
        
        if regime_data.empty:
            return RegimeDetectionResult(
                regime_type=CorrelationRegime.NORMAL,
                start_date=regime['start'],
                end_date=regime['end'],
                confidence=0.5,
                characteristics={},
                assets_affected=[]
            )
            
        # Calculate regime characteristics
        mean_corr = regime_data.mean()
        std_corr = regime_data.std()
        trend = self._calculate_trend(regime_data)
        
        # Classify based on characteristics
        if std_corr > correlation_series.std() * 1.5:
            regime_type = CorrelationRegime.VOLATILE
            confidence = 0.7
        elif mean_corr > 0.7:
            regime_type = CorrelationRegime.CRISIS
            confidence = 0.8
        elif mean_corr < 0.2:
            regime_type = CorrelationRegime.DECOUPLING
            confidence = 0.6
        elif trend > 0.1:
            regime_type = CorrelationRegime.TRENDING
            confidence = 0.65
        elif trend < -0.1:
            regime_type = CorrelationRegime.DIVERGING
            confidence = 0.65
        else:
            regime_type = CorrelationRegime.NORMAL
            confidence = 0.5
            
        # Check for seasonal patterns
        if self._detect_seasonal_pattern(regime_data):
            regime_type = CorrelationRegime.SEASONAL
            confidence = 0.6

        characteristics = {
            'mean_correlation': mean_corr,
            'std_correlation': std_corr,
            'trend': trend,
            'duration_days': (regime['end'] - regime['start']).days
        }

        return RegimeDetectionResult(
            regime_type=regime_type,
            start_date=regime['start'],
            end_date=regime['end'],
            confidence=confidence,
            characteristics=characteristics,
            assets_affected=[]
        )

    def _calculate_trend(self, series: pd.Series) -> float:
        """
        Calculate linear trend of a series.

        Returns slope normalized by standard deviation.
        """
        if len(series) < 2:
            return 0.0

        x = np.arange(len(series))
        y = series.values

        # Remove NaN
        mask = ~np.isnan(y)
        if mask.sum() < 2:
            return 0.0

        slope, _, _, _, _ = stats.linregress(x[mask], y[mask])

        # Normalize by std to get comparable trend magnitude
        std = series.std()
        if std == 0:
            return 0.0

        return slope * len(series) / std

    def _detect_seasonal_pattern(self, series: pd.Series) -> bool:
        """
        Detect if a series exhibits seasonal patterns using autocorrelation peaks.

        Returns True if significant periodic pattern is found.
        """
        if len(series) < 30:
            return False

        try:
            values = series.dropna().values
            # Compute autocorrelation
            n = len(values)
            mean = np.mean(values)
            var = np.var(values)

            if var == 0:
                return False

            autocorr = np.correlate(values - mean, values - mean, mode='full')
            autocorr = autocorr[n - 1:] / (var * n)

            # Look for significant peaks in autocorrelation (beyond lag 5)
            if len(autocorr) > 10:
                peaks, properties = find_peaks(autocorr[5:], height=0.3)
                return len(peaks) > 0

        except Exception:
            pass

        return False

    def _adjust_probs_with_conditions(
        self,
        probs: pd.Series,
        market_conditions: Dict
    ) -> pd.Series:
        """
        Adjust transition probabilities based on current market conditions.

        Args:
            probs: Base transition probabilities
            market_conditions: Dict with keys like 'volatility', 'trend', 'volume'

        Returns:
            Adjusted probability series
        """
        adjusted = probs.copy()

        # High volatility increases probability of crisis/volatile regimes
        if market_conditions.get('volatility', 0) > 0.7:
            for regime in adjusted.index:
                regime_str = regime if isinstance(regime, str) else regime.value
                if regime_str in ('crisis', 'volatile'):
                    adjusted[regime] *= 1.5
                elif regime_str == 'normal':
                    adjusted[regime] *= 0.7

        # Strong negative trend increases probability of diverging
        if market_conditions.get('trend', 0) < -0.5:
            for regime in adjusted.index:
                regime_str = regime if isinstance(regime, str) else regime.value
                if regime_str == 'diverging':
                    adjusted[regime] *= 1.3

        # Low volatility increases probability of normal/decoupling
        if market_conditions.get('volatility', 0) < 0.3:
            for regime in adjusted.index:
                regime_str = regime if isinstance(regime, str) else regime.value
                if regime_str in ('normal', 'decoupling'):
                    adjusted[regime] *= 1.3

        # Renormalize to sum to 1
        total = adjusted.sum()
        if total > 0:
            adjusted = adjusted / total

        return adjusted