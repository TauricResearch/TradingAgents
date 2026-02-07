"""
Correlation Analyzer
Core engine for cross-asset correlation analysis.

Implements multiple correlation techniques:
1. Pearson correlation for linear relationships
2. Spearman rank correlation for monotonic relationships  
3. Dynamic Conditional Correlation (DCC-GARCH)
4. Wavelet coherence for multi-timescale analysis
5. Lead-lag correlation with time shifts

Based on academic research:
- Engle (2002): Dynamic Conditional Correlation
- Grinsted et al. (2004): Wavelet coherence for geophysical time series
- Alexander (2001): Correlation and cointegration in financial markets
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Union
from dataclasses import dataclass
from enum import Enum
import warnings
from scipy import stats
from scipy.signal import correlate
import pywt  # wavelet transform


class CorrelationMethod(Enum):
    """Correlation calculation methods."""
    PEARSON = "pearson"
    SPEARMAN = "spearman"
    KENDALL = "kendall"
    DCC_GARCH = "dcc_garch"
    WAVELET = "wavelet"
    LEAD_LAG = "lead_lag"


@dataclass
class CorrelationResult:
    """Container for correlation analysis results."""
    assets: Tuple[str, str]
    method: CorrelationMethod
    correlation: float
    p_value: Optional[float] = None
    confidence_interval: Optional[Tuple[float, float]] = None
    lag: Optional[int] = None  # for lead-lag analysis
    time_scale: Optional[float] = None  # for wavelet analysis
    metadata: Optional[Dict] = None


class CorrelationAnalyzer:
    """Main correlation analysis engine."""
    
    def __init__(self, min_data_points: int = 30, significance_level: float = 0.05):
        """
        Initialize the correlation analyzer.
        
        Args:
            min_data_points: Minimum data points required for analysis
            significance_level: Statistical significance level for p-values
        """
        self.min_data_points = min_data_points
        self.significance_level = significance_level
        
    def analyze_pair(
        self,
        asset1_prices: pd.Series,
        asset2_prices: pd.Series,
        methods: List[CorrelationMethod] = None,
        max_lag: int = 10
    ) -> List[CorrelationResult]:
        """
        Analyze correlation between two asset price series.
        
        Args:
            asset1_prices: Price series for first asset
            asset2_prices: Price series for second asset  
            methods: List of correlation methods to apply
            max_lag: Maximum lag for lead-lag analysis
            
        Returns:
            List of correlation results for each method
        """
        if methods is None:
            methods = [
                CorrelationMethod.PEARSON,
                CorrelationMethod.SPEARMAN,
                CorrelationMethod.LEAD_LAG
            ]
        
        # Validate input data
        self._validate_input(asset1_prices, asset2_prices)
        
        # Align time series
        aligned_data = self._align_series(asset1_prices, asset2_prices)
        if aligned_data is None:
            return []
            
        asset1_aligned, asset2_aligned = aligned_data
        
        results = []
        
        for method in methods:
            try:
                if method == CorrelationMethod.PEARSON:
                    result = self._pearson_correlation(asset1_aligned, asset2_aligned)
                elif method == CorrelationMethod.SPEARMAN:
                    result = self._spearman_correlation(asset1_aligned, asset2_aligned)
                elif method == CorrelationMethod.KENDALL:
                    result = self._kendall_correlation(asset1_aligned, asset2_aligned)
                elif method == CorrelationMethod.LEAD_LAG:
                    result = self._lead_lag_correlation(asset1_aligned, asset2_aligned, max_lag)
                elif method == CorrelationMethod.DCC_GARCH:
                    result = self._dcc_garch_correlation(asset1_aligned, asset2_aligned)
                elif method == CorrelationMethod.WAVELET:
                    result = self._wavelet_coherence(asset1_aligned, asset2_aligned)
                else:
                    continue
                    
                results.append(result)
                
            except Exception as e:
                warnings.warn(f"Failed to compute {method.value} correlation: {e}")
                continue
                
        return results
    
    def analyze_portfolio(
        self,
        price_data: pd.DataFrame,
        methods: List[CorrelationMethod] = None
    ) -> pd.DataFrame:
        """
        Analyze correlation matrix for multiple assets.
        
        Args:
            price_data: DataFrame with assets as columns and prices as rows
            methods: Correlation methods to apply
            
        Returns:
            Correlation matrix DataFrame
        """
        if methods is None:
            methods = [CorrelationMethod.PEARSON]
            
        assets = price_data.columns.tolist()
        n_assets = len(assets)
        
        # Initialize correlation matrix
        corr_matrix = pd.DataFrame(
            np.eye(n_assets),
            index=assets,
            columns=assets
        )
        
        # Fill correlation matrix
        for i in range(n_assets):
            for j in range(i + 1, n_assets):
                asset_i = price_data.iloc[:, i]
                asset_j = price_data.iloc[:, j]
                
                results = self.analyze_pair(asset_i, asset_j, methods)
                if results:
                    # Use first method's correlation
                    corr_value = results[0].correlation
                    corr_matrix.iloc[i, j] = corr_value
                    corr_matrix.iloc[j, i] = corr_value
                    
        return corr_matrix
    
    def rolling_correlation(
        self,
        asset1_prices: pd.Series,
        asset2_prices: pd.Series,
        window: int = 20,
        method: CorrelationMethod = CorrelationMethod.PEARSON
    ) -> pd.Series:
        """
        Compute rolling correlation between two assets.
        
        Args:
            asset1_prices: Price series for first asset
            asset2_prices: Price series for second asset
            window: Rolling window size
            method: Correlation method to use
            
        Returns:
            Series of rolling correlation values
        """
        aligned_data = self._align_series(asset1_prices, asset2_prices)
        if aligned_data is None:
            return pd.Series([], dtype=float)
            
        asset1_aligned, asset2_aligned = aligned_data
        
        # Create DataFrame for rolling calculation
        df = pd.DataFrame({
            'asset1': asset1_aligned,
            'asset2': asset2_aligned
        })
        
        if method == CorrelationMethod.PEARSON:
            return df['asset1'].rolling(window).corr(df['asset2'])
        elif method == CorrelationMethod.SPEARMAN:
            # Spearman rolling correlation
            rolling_corr = []
            for i in range(len(df) - window + 1):
                window_data = df.iloc[i:i + window]
                corr, _ = stats.spearmanr(window_data['asset1'], window_data['asset2'])
                rolling_corr.append(corr)
            return pd.Series(rolling_corr, index=df.index[window - 1:])
        else:
            raise ValueError(f"Rolling correlation not implemented for {method}")
    
    def _validate_input(self, series1: pd.Series, series2: pd.Series):
        """Validate input time series."""
        if len(series1) < self.min_data_points or len(series2) < self.min_data_points:
            raise ValueError(
                f"Insufficient data points. Minimum required: {self.min_data_points}"
            )
        
        if series1.isnull().all() or series2.isnull().all():
            raise ValueError("Input series contain only NaN values")
    
    def _align_series(self, series1: pd.Series, series2: pd.Series) -> Optional[Tuple[pd.Series, pd.Series]]:
        """Align two time series on their index."""
        # Convert to DataFrame and drop NaN
        df = pd.DataFrame({'s1': series1, 's2': series2})
        df = df.dropna()
        
        if len(df) < self.min_data_points:
            return None
            
        return df['s1'], df['s2']
    
    def _pearson_correlation(self, series1: pd.Series, series2: pd.Series) -> CorrelationResult:
        """Compute Pearson correlation."""
        corr, p_value = stats.pearsonr(series1, series2)
        
        # Calculate confidence interval using Fisher transformation
        n = len(series1)
        z = np.arctanh(corr)
        se = 1 / np.sqrt(n - 3)
        z_lower = z - 1.96 * se
        z_upper = z + 1.96 * se
        ci = (np.tanh(z_lower), np.tanh(z_upper))
        
        return CorrelationResult(
            assets=(series1.name, series2.name),
            method=CorrelationMethod.PEARSON,
            correlation=corr,
            p_value=p_value,
            confidence_interval=ci,
            metadata={'n_observations': n}
        )
    
    def _spearman_correlation(self, series1: pd.Series, series2: pd.Series) -> CorrelationResult:
        """Compute Spearman rank correlation."""
        corr, p_value = stats.spearmanr(series1, series2)
        
        return CorrelationResult(
            assets=(series1.name, series2.name),
            method=CorrelationMethod.SPEARMAN,
            correlation=corr,
            p_value=p_value,
            metadata={'n_observations': len(series1)}
        )
    
    def _kendall_correlation(self, series1: pd.Series, series2: pd.Series) -> CorrelationResult:
        """Compute Kendall's tau correlation."""
        corr, p_value = stats.kendalltau(series1, series2)
        
        return CorrelationResult(
            assets=(series1.name, series2.name),
            method=CorrelationMethod.KENDALL,
            correlation=corr,
            p_value=p_value,
            metadata={'n_observations': len(series1)}
        )
    
    def _lead_lag_correlation(
        self,
        series1: pd.Series,
        series2: pd.Series,
        max_lag: int
    ) -> CorrelationResult:
        """
        Compute lead-lag correlation to find optimal time shift.
        
        Returns correlation at optimal lag where series1 leads series2.
        """
        # Normalize series
        s1_norm = (series1 - series1.mean()) / series1.std()
        s2_norm = (series2 - series2.mean()) / series2.std()
        
        # Compute cross-correlation
        corr_values = correlate(s1_norm, s2_norm, mode='full')
        lags = np.arange(-max_lag, max_lag + 1)
        
        # Find lag with maximum correlation
        max_corr_idx = np.argmax(np.abs(corr_values))
        optimal_lag = lags[max_corr_idx]
        max_corr = corr_values[max_corr_idx] / len(series1)
        
        # Determine lead/lag relationship
        if optimal_lag < 0:
            relationship = f"Asset1 leads Asset2 by {-optimal_lag} periods"
        elif optimal_lag > 0:
            relationship = f"Asset2 leads Asset1 by {optimal_lag} periods"
        else:
            relationship = "No significant lead-lag relationship"
        
        return CorrelationResult(
            assets=(series1.name, series2.name),
            method=CorrelationMethod.LEAD_LAG,
            correlation=max_corr,
            lag=optimal_lag,
            metadata={
                'relationship': relationship,
                'max_lag_considered': max_lag,
                'n_observations': len(series1)
            }
        )
    
    def _dcc_garch_correlation(self, series1: pd.Series, series2: pd.Series) -> CorrelationResult:
        """
        Compute Dynamic Conditional Correlation using GARCH model.
        
        Simplified implementation - in production would use arch package.
        """
        # Calculate returns
        returns1 = series1.pct_change().dropna()
        returns2 = series2.pct_change().dropna()
        
        # Align returns
        returns_df = pd.DataFrame({'r1': returns1, 'r2': returns2}).dropna()
        
        if len(returns_df) < 50:  # Need sufficient data for GARCH
            raise ValueError("Insufficient data for DCC-GARCH estimation")
        
        # Simplified DCC calculation
        # In practice, would use: from arch import arch_model
        ewma_corr = returns_df['r1'].ewm(span=20).corr(returns_df['r2']).iloc[-1]
        
        return CorrelationResult(
            assets=(series1.name, series2.name),
            method=CorrelationMethod.DCC_GARCH,
            correlation=ewma_corr,
            metadata={
                'method': 'simplified_ewma_approximation',
                'n_observations': len(returns_df)
            }
        )
    
    def _wavelet_coherence(self, series1: pd.Series, series2: pd.Series) -> CorrelationResult:
        """
        Compute wavelet coherence for multi-timescale analysis.
        
        Based on Grinsted et al. (2004) method.
        """
        try:
            # Ensure equal length
            min_len = min(len(series1), len(series2))
            s1 = series1.values[:min_len]
            s2 = series2.values[:min_len]
            
            # Normalize
            s1_norm = (s1 - np.mean(s1)) / np.std(s1)
            s2_norm = (s2 - np.mean(s2)) / np.std(s2)
            
            # Continuous wavelet transform
            scales = np.arange(1, 65)  # 64 scales for multi-resolution
            coefficients1, _ = pywt.cwt(s1_norm, scales, 'morl')
            coefficients2, _ = pywt.cwt(s2_norm, scales, 'morl')
            
            # Wavelet coherence
            power1 = np.abs(coefficients1) ** 2
            power2 = np.abs(coefficients2) ** 2
            cross_power = coefficients1 * np.conj(coefficients2)
            
            # Smoothing
            smooth = lambda x: np.convolve(x, np.ones(3)/3, mode='same')
            smooth_power1 = np.apply_along_axis(smooth, 1, power1)
            smooth_power2 = np.apply_along_axis(smooth, 1, power2)
            smooth_cross = np.apply_along_axis(smooth, 1, cross_power)
            
            # Coherence
            coherence = np.abs(smooth_cross) ** 2 / (smooth_power1 * smooth_power2)
            
            # Average coherence across scales
            avg_coherence = np.nanmean(coherence)
            
            # Find dominant time scale
            scale_power = np.nanmean(coherence, axis=1)
            dominant_scale_idx = np.nanargmax(scale_power)
            dominant_scale = scales[dominant_scale_idx]
            
            return CorrelationResult(
                assets=(series1.name, series2.name),
                method=CorrelationMethod.WAVELET,
                correlation=avg_coherence,
                time_scale=dominant_scale,
                metadata={
                    'n_scales': len(scales),
                    'dominant_scale': dominant_scale,
                    'n_observations': min_len
                }
            )
            
        except Exception as e:
            raise ValueError(f"Wavelet coherence computation failed: {e}")