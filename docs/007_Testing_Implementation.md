# チケット #007: テスト実装

## 概要
バックテスト機能の品質保証のための包括的なテストスイートの実装

## 目的
- コードの信頼性確保
- リグレッション防止
- エッジケースの検証
- 計算精度の保証

## 実装要件

### 1. テスト構造

```
tests/
├── unit/
│   ├── test_ta_flow_strategy.py
│   ├── test_backtest_engine.py
│   ├── test_metrics_calculator.py
│   ├── test_persistence.py
│   └── test_output_features.py
├── integration/
│   ├── test_cli_commands.py
│   ├── test_full_backtest.py
│   └── test_data_flow.py
├── fixtures/
│   ├── sample_data.py
│   └── mock_responses.py
└── conftest.py  # pytest設定
```

### 2. ユニットテスト

#### TAFlowStrategy テスト
```python
class TestTAFlowStrategy:
    def test_initialization(self):
        """設定の正しい初期化"""
        pass
    
    def test_offline_mode_enforcement(self):
        """オフラインモードの強制確認"""
        pass
    
    def test_decide_returns_valid_signal(self):
        """Buy/Sell/Holdの返却確認"""
        pass
    
    def test_error_handling(self):
        """エラー時のフォールバック"""
        pass
```

#### BacktestEngine テスト
```python
class TestBacktestEngine:
    def test_position_transitions(self):
        """ポジション遷移の正確性"""
        # None -> Long
        # Long -> Short
        # Short -> None
        # etc.
        pass
    
    def test_fee_calculation(self):
        """手数料計算の検証"""
        pass
    
    def test_slippage_calculation(self):
        """スリッページ計算の検証"""
        pass
    
    def test_capital_management(self):
        """資金管理の正確性"""
        pass
```

#### MetricsCalculator テスト
```python
class TestMetricsCalculator:
    @pytest.mark.parametrize("equity_curve,expected_return", [
        ([100000, 110000], 0.10),
        ([100000, 90000], -0.10),
    ])
    def test_total_return_calculation(self, equity_curve, expected_return):
        """累積リターン計算の検証"""
        pass
    
    def test_sharpe_ratio_calculation(self):
        """シャープレシオ計算の検証"""
        pass
    
    def test_max_drawdown_calculation(self):
        """最大ドローダウン計算の検証"""
        pass
    
    def test_edge_cases(self):
        """エッジケース（ゼロ除算等）"""
        pass
```

### 3. 統合テスト

```python
class TestFullBacktest:
    def test_end_to_end_backtest(self):
        """完全なバックテストフローの検証"""
        # 1. モックデータの準備
        # 2. バックテスト実行
        # 3. 結果の検証
        # 4. 永続化確認
        pass
    
    def test_cli_integration(self):
        """CLIコマンドの統合テスト"""
        result = runner.invoke(cli, [
            'backtest',
            '--ticker', 'AAPL',
            '--start', '2024-01-01',
            '--end', '2024-03-31'
        ])
        assert result.exit_code == 0
```

### 4. パフォーマンステスト

```python
class TestPerformance:
    def test_large_dataset_performance(self):
        """大規模データでのパフォーマンス"""
        # 10年分のデータでも1分以内
        pass
    
    def test_memory_usage(self):
        """メモリ使用量の監視"""
        pass
```

### 5. モックとフィクスチャ

```python
# fixtures/sample_data.py
@pytest.fixture
def sample_price_data():
    """サンプル価格データ"""
    return pd.DataFrame({
        'Date': pd.date_range('2024-01-01', periods=100),
        'Open': np.random.rand(100) * 100 + 100,
        'High': np.random.rand(100) * 100 + 110,
        'Low': np.random.rand(100) * 100 + 90,
        'Close': np.random.rand(100) * 100 + 100,
        'Volume': np.random.randint(1000000, 10000000, 100)
    })

@pytest.fixture
def mock_ta_strategy():
    """モックストラテジー"""
    strategy = Mock(spec=TAFlowStrategy)
    strategy.decide.side_effect = cycle(['Buy', 'Hold', 'Sell'])
    return strategy
```

### 6. カバレッジ目標

```yaml
# .coveragerc
[run]
source = tradingagents.backtest
omit = 
    */tests/*
    */migrations/*

[report]
precision = 2
fail_under = 80  # 80%以上のカバレッジ必須
```

## 受け入れ条件
- [ ] 全モジュールのユニットテスト作成
- [ ] コードカバレッジ80%以上
- [ ] 統合テストの成功
- [ ] エッジケースの網羅
- [ ] CI/CDでの自動実行設定
- [ ] テストドキュメントの作成

## 依存関係
- pytest
- pytest-cov（カバレッジ）
- pytest-mock（モック）
- pytest-benchmark（パフォーマンス）

## タスク
- [ ] テストディレクトリ構造の作成
- [ ] pytest設定ファイル作成
- [ ] TAFlowStrategyのテスト実装
- [ ] BacktestEngineのテスト実装
- [ ] MetricsCalculatorのテスト実装
- [ ] 永続化機能のテスト実装
- [ ] 統合テストの実装
- [ ] フィクスチャとモックの作成
- [ ] カバレッジ設定
- [ ] CI設定（GitHub Actions等）