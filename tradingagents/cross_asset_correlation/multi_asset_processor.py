"""
Multi-Asset Processor
Handles processing of multiple asset classes and data sources.

Supports:
- Multiple asset classes (stocks, ETFs, commodities, currencies, crypto)
- Different data frequencies (daily, hourly, minute)
- Missing data imputation
- Returns calculation and normalization
- Asset classification and grouping

Based on research in multi-asset portfolio optimization.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import warnings
from datetime import datetime, timedelta


class AssetClass(Enum):
    """Asset classification categories."""
    STOCK = "stock"
    ETF = "etf"
    COMMODITY = "commodity"
    CURRENCY = "currency"
    CRYPTO = "cryptocurrency"
    BOND = "bond"
    INDEX = "index"
    FUTURE = "future"
    OPTION = "option"


class DataFrequency(Enum):
    """Data frequency options."""
    DAILY = "daily"
    HOURLY = "hourly"
    MINUTE_30 = "30min"
    MINUTE_15 = "15min"
    MINUTE_5 = "5min"
    MINUTE_1 = "1min"


@dataclass
class AssetMetadata:
    """Metadata for financial assets."""
    symbol: str
    name: str
    asset_class: AssetClass
    sector: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    currency: Optional[str] = None
    market_cap: Optional[float] = None
    volume_avg: Optional[float] = None
    data_source: Optional[str] = None


class MultiAssetProcessor:
    """Processor for handling multiple asset data."""
    
    def __init__(self, default_frequency: DataFrequency = DataFrequency.DAILY):
        """
        Initialize multi-asset processor.
        
        Args:
            default_frequency: Default data frequency for processing
        """
        self.default_frequency = default_frequency
        self.asset_metadata: Dict[str, AssetMetadata] = {}
        
    def load_price_data(
        self,
        price_data: pd.DataFrame,
        metadata: Optional[Dict[str, AssetMetadata]] = None
    ) -> pd.DataFrame:
        """
        Load and validate price data for multiple assets.
        
        Args:
            price_data: DataFrame with assets as columns and prices as rows
            metadata: Optional metadata for each asset
            
        Returns:
            Cleaned and validated price DataFrame
        """
        # Validate input
        if price_data.empty:
            raise ValueError("Price data is empty")
            
        if price_data.isnull().all().all():
            raise ValueError("All price data is NaN")
            
        # Store metadata if provided
        if metadata:
            self.asset_metadata.update(metadata)
            
        # Fill missing metadata
        for symbol in price_data.columns:
            if symbol not in self.asset_metadata:
                self.asset_metadata[symbol] = AssetMetadata(
                    symbol=symbol,
                    name=symbol,
                    asset_class=self._infer_asset_class(symbol)
                )
                
        # Clean data
        cleaned_data = self._clean_price_data(price_data)
        
        return cleaned_data
    
    def calculate_returns(
        self,
        price_data: pd.DataFrame,
        return_type: str = "log",
        fill_na: bool = True
    ) -> pd.DataFrame:
        """
        Calculate returns from price data.
        
        Args:
            price_data: Price DataFrame
            return_type: Type of returns ('log' or 'simple')
            fill_na: Whether to fill NaN returns with zeros
            
        Returns:
            Returns DataFrame
        """
        if return_type == "log":
            returns = np.log(price_data / price_data.shift(1))
        elif return_type == "simple":
            returns = price_data.pct_change()
        else:
            raise ValueError(f"Unknown return type: {return_type}")
            
        # Remove first row (NaN)
        returns = returns.iloc[1:]
        
        if fill_na:
            returns = returns.fillna(0)
            
        return returns
    
    def resample_data(
        self,
        data: pd.DataFrame,
        target_frequency: DataFrequency,
        aggregation: str = "last"
    ) -> pd.DataFrame:
        """
        Resample data to different frequency.
        
        Args:
            data: Input DataFrame with datetime index
            target_frequency: Target frequency for resampling
            aggregation: Aggregation method ('last', 'mean', 'ohlc')
            
        Returns:
            Resampled DataFrame
        """
        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError("Data must have DatetimeIndex for resampling")
            
        # Map frequency to pandas offset
        freq_map = {
            DataFrequency.DAILY: 'D',
            DataFrequency.HOURLY: 'H',
            DataFrequency.MINUTE_30: '30min',
            DataFrequency.MINUTE_15: '15min',
            DataFrequency.MINUTE_5: '5min',
            DataFrequency.MINUTE_1: '1min'
        }
        
        freq_str = freq_map.get(target_frequency)
        if not freq_str:
            raise ValueError(f"Unsupported frequency: {target_frequency}")
            
        if aggregation == "last":
            resampled = data.resample(freq_str).last()
        elif aggregation == "mean":
            resampled = data.resample(freq_str).mean()
        elif aggregation == "ohlc":
            # For OHLC resampling
            resampled = pd.DataFrame()
            for col in data.columns:
                ohlc = data[col].resample(freq_str).ohlc()
                resampled[f"{col}_open"] = ohlc['open']
                resampled[f"{col}_high"] = ohlc['high']
                resampled[f"{col}_low"] = ohlc['low']
                resampled[f"{col}_close"] = ohlc['close']
        else:
            raise ValueError(f"Unknown aggregation: {aggregation}")
            
        return resampled.dropna()
    
    def align_time_series(
        self,
        dataframes: List[pd.DataFrame],
        method: str = "inner"
    ) -> List[pd.DataFrame]:
        """
        Align multiple time series to common index.
        
        Args:
            dataframes: List of DataFrames to align
            method: Alignment method ('inner' or 'outer')
            
        Returns:
            List of aligned DataFrames
        """
        if not dataframes:
            return []
            
        # Get common index
        indices = [df.index for df in dataframes]
        
        if method == "inner":
            common_index = indices[0]
            for idx in indices[1:]:
                common_index = common_index.intersection(idx)
        elif method == "outer":
            common_index = indices[0]
            for idx in indices[1:]:
                common_index = common_index.union(idx)
        else:
            raise ValueError(f"Unknown alignment method: {method}")
            
        # Align each DataFrame
        aligned_dfs = []
        for df in dataframes:
            aligned = df.reindex(common_index)
            aligned_dfs.append(aligned)
            
        return aligned_dfs
    
    def detect_asset_groups(
        self,
        correlation_matrix: pd.DataFrame,
        threshold: float = 0.7,
        method: str = "hierarchical"
    ) -> List[List[str]]:
        """
        Detect groups of highly correlated assets.
        
        Args:
            correlation_matrix: Correlation matrix DataFrame
            threshold: Correlation threshold for grouping
            method: Grouping method ('hierarchical' or 'connected_components')
            
        Returns:
            List of asset groups (lists of symbols)
        """
        if method == "hierarchical":
            return self._hierarchical_clustering(correlation_matrix, threshold)
        elif method == "connected_components":
            return self._connected_components(correlation_matrix, threshold)
        else:
            raise ValueError(f"Unknown grouping method: {method}")
    
    def calculate_correlation_stability(
        self,
        price_data: pd.DataFrame,
        window: int = 60,
        step: int = 5
    ) -> pd.DataFrame:
        """
        Calculate stability of correlations over time.
        
        Args:
            price_data: Price DataFrame
            window: Rolling window size
            step: Step between windows
            
        Returns:
            DataFrame with correlation stability metrics
        """
        returns = self.calculate_returns(price_data)
        n_periods = len(returns)
        
        stability_metrics = {}
        
        for i in range(0, n_periods - window, step):
            window_data = returns.iloc[i:i + window]
            corr_matrix = window_data.corr()
            
            # Flatten correlation matrix (excluding diagonal)
            corr_values = corr_matrix.values[np.triu_indices_from(corr_matrix, k=1)]
            
            # Calculate stability metrics for this window
            stability_metrics[f"window_{i}"] = {
                'mean_correlation': np.mean(corr_values),
                'std_correlation': np.std(corr_values),
                'min_correlation': np.min(corr_values),
                'max_correlation': np.max(corr_values),
                'positive_ratio': np.sum(corr_values > 0) / len(corr_values),
                'start_date': returns.index[i],
                'end_date': returns.index[i + window - 1]
            }
            
        return pd.DataFrame(stability_metrics).T
    
    def get_asset_class_correlations(
        self,
        price_data: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Calculate average correlations within and between asset classes.
        
        Args:
            price_data: Price DataFrame with assets as columns
            
        Returns:
            DataFrame of asset class correlations
        """
        # Get returns
        returns = self.calculate_returns(price_data)
        
        # Get asset classes
        asset_classes = {}
        for symbol in returns.columns:
            if symbol in self.asset_metadata:
                asset_classes[symbol] = self.asset_metadata[symbol].asset_class
            else:
                asset_classes[symbol] = AssetClass.STOCK
                
        # Calculate correlation matrix
        corr_matrix = returns.corr()
        
        # Group by asset class
        unique_classes = set(asset_classes.values())
        class_correlations = pd.DataFrame(
            index=unique_classes,
            columns=unique_classes
        )
        
        for class1 in unique_classes:
            for class2 in unique_classes:
                # Get assets in each class
                assets1 = [a for a, c in asset_classes.items() if c == class1]
                assets2 = [a for a, c in asset_classes.items() if c == class2]
                
                if not assets1 or not assets2:
                    class_correlations.loc[class1, class2] = np.nan
                    continue
                    
                # Get correlations between classes
                class_corr_values = []
                for a1 in assets1:
                    for a2 in assets2:
                        if a1 != a2:  # Exclude self-correlation
                            corr_value = corr_matrix.loc[a1, a2]
                            if not np.isnan(corr_value):
                                class_corr_values.append(corr_value)
                                
                if class_corr_values:
                    class_correlations.loc[class1, class2] = np.mean(class_corr_values)
                else:
                    class_correlations.loc[class1, class2] = np.nan
                    
        return class_correlations
    
    def _clean_price_data(self, price_data: pd.DataFrame) -> pd.DataFrame:
        """Clean and validate price data."""
        # Remove columns with all NaN
        price_data = price_data.dropna(axis=1, how='all')
        
        # Forward fill for small gaps (up to 2 periods)
        price_data = price_data.ffill(limit=2)
        
        # Remove any remaining NaN
        price_data = price_data.dropna()
        
        # Ensure prices are positive
        if (price_data <= 0).any().any():
            warnings.warn("Some prices are non-positive. Taking absolute values.")
            price_data = price_data.abs()
            
        return price_data
    
    def _infer_asset_class(self, symbol: str) -> AssetClass:
        """Infer asset class from symbol."""
        symbol_lower = symbol.lower()
        
        # Common patterns
        if any(x in symbol_lower for x in ['.us', '.nyse', '.nasdaq']):
            return AssetClass.STOCK
        elif symbol_lower.endswith('=x'):
            return AssetClass.CURRENCY
        elif any(x in symbol_lower for x in ['btc', 'eth', 'xrp', 'crypto']):
            return AssetClass.CRYPTO
        elif any(x in symbol_lower for x in ['etf', 'ivv', 'spy', 'qqq']):
            return AssetClass.ETF
        elif any(x in symbol_lower for x in ['gold', 'silver', 'oil', 'commodity']):
            return AssetClass.COMMODITY
        elif any(x in symbol_lower for x in ['^', 'index', '.indx']):
            return AssetClass.INDEX
        else:
            return AssetClass.STOCK  # Default
    
    def _hierarchical_clustering(
        self,
        correlation_matrix: pd.DataFrame,
        threshold: float
    ) -> List[List[str]]:
        """Group assets using hierarchical clustering."""
        from scipy.cluster.hierarchy import linkage, fcluster
        from scipy.spatial.distance import squareform
        
        # Convert correlation to distance (1 - |correlation|)
        distance_matrix = 1 - np.abs(correlation_matrix.values)
        
        # Perform hierarchical clustering
        linkage_matrix = linkage(squareform(distance_matrix), method='average')
        
        # Form clusters at threshold
        clusters = fcluster(linkage_matrix, 1 - threshold, criterion='distance')
        
        # Group assets by cluster
        asset_groups = {}
        for asset, cluster_id in zip(correlation_matrix.columns, clusters):
            if cluster_id not in asset_groups:
                asset_groups[cluster_id] = []
            asset_groups[cluster_id].append(asset)
            
        return list(asset_groups.values())
    
    def _connected_components(
        self,
        correlation_matrix: pd.DataFrame,
        threshold: float
    ) -> List[List[str]]:
        """Group assets using graph connected components."""
        import networkx as nx
        
        # Create graph
        G = nx.Graph()
        
        # Add nodes (assets)
        for asset in correlation_matrix.columns:
            G.add_node(asset)
            
        # Add edges for high correlations
        n_assets = len(correlation_matrix.columns)
        for i in range(n_assets):
            for j in range(i + 1, n_assets):
                asset_i = correlation_matrix.columns[i]
                asset_j = correlation_matrix.columns[j]
                corr = abs(correlation_matrix.iloc[i, j])
                
                if corr >= threshold:
                    G.add_edge(asset_i, asset_j)
                    
        # Find connected components
        components = list(nx.connected_components(G))
        
        # Convert to lists
        return [list(comp) for comp in components]