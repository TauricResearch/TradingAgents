# チケット #006: 永続化機能実装

## 概要
バックテスト結果をデータベースに保存し、過去の実行結果を管理・比較可能にする機能の実装

## 目的
- 実行結果の永続化による履歴管理
- 過去結果の検索と参照
- 複数結果の比較分析
- 結果の再現性確保

## 実装要件

### 1. データベース設計

#### SQLiteスキーマ
```sql
-- バックテスト実行記録
CREATE TABLE backtests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker VARCHAR(10) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_capital DECIMAL(10,2) NOT NULL,
    final_capital DECIMAL(10,2) NOT NULL,
    fee_rate DECIMAL(5,4) NOT NULL,
    slippage_rate DECIMAL(5,4) NOT NULL,
    
    -- 評価指標
    total_return DECIMAL(10,4),
    annual_return DECIMAL(10,4),
    sharpe_ratio DECIMAL(10,4),
    max_drawdown DECIMAL(10,4),
    win_rate DECIMAL(10,4),
    profit_factor DECIMAL(10,4),
    total_trades INTEGER,
    
    -- Buy & Hold比較
    buyhold_return DECIMAL(10,4),
    buyhold_sharpe DECIMAL(10,4),
    
    -- メタデータ
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    execution_time_sec DECIMAL(10,2),
    llm_model VARCHAR(50),
    config_json TEXT,  -- 完全な設定のJSON
    
    INDEX idx_ticker_date (ticker, start_date, end_date)
);

-- 個別取引記録
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backtest_id INTEGER NOT NULL,
    trade_date DATE NOT NULL,
    action VARCHAR(10) NOT NULL,  -- 'buy', 'sell'
    price DECIMAL(10,4) NOT NULL,
    shares DECIMAL(10,4) NOT NULL,
    fee DECIMAL(10,4) NOT NULL,
    slippage DECIMAL(10,4) NOT NULL,
    capital_after DECIMAL(10,2) NOT NULL,
    
    FOREIGN KEY (backtest_id) REFERENCES backtests(id),
    INDEX idx_backtest_id (backtest_id)
);

-- 日次パフォーマンス記録（オプション）
CREATE TABLE daily_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backtest_id INTEGER NOT NULL,
    date DATE NOT NULL,
    equity DECIMAL(10,2) NOT NULL,
    daily_return DECIMAL(10,6),
    drawdown DECIMAL(10,6),
    
    FOREIGN KEY (backtest_id) REFERENCES backtests(id),
    INDEX idx_backtest_date (backtest_id, date)
);
```

### 2. データアクセス層

```python
class BacktestRepository:
    def __init__(self, db_path: str = "results.sqlite"):
        self.db_path = db_path
        self._init_database()
    
    def save_backtest(self, 
                     result: BacktestResult,
                     config: dict) -> int:
        """
        バックテスト結果を保存
        
        Returns:
            backtest_id: 保存されたレコードのID
        """
        pass
    
    def get_backtest(self, backtest_id: int) -> BacktestResult:
        """
        IDから結果を取得
        """
        pass
    
    def list_backtests(self,
                      ticker: str = None,
                      start_date: str = None,
                      end_date: str = None,
                      limit: int = 100) -> List[BacktestSummary]:
        """
        条件に合うバックテストの一覧
        """
        pass
    
    def compare_backtests(self,
                         id1: int,
                         id2: int) -> ComparisonResult:
        """
        2つのバックテスト結果を比較
        """
        pass
```

### 3. Parquetファイル形式サポート（オプション）

```python
class ParquetPersistence:
    def save_to_parquet(self,
                       result: BacktestResult,
                       output_dir: str = "results/"):
        """
        大規模データ向けのParquet形式保存
        
        ファイル構造:
        results/
        ├── metadata.parquet  # バックテストメタデータ
        ├── trades/
        │   └── {backtest_id}.parquet
        └── daily_performance/
            └── {backtest_id}.parquet
        """
        pass
```

### 4. データ移行とバックアップ

```python
class DataMigration:
    def export_to_csv(self, backtest_id: int, output_dir: str):
        """
        特定のバックテスト結果をCSVエクスポート
        """
        pass
    
    def import_from_csv(self, csv_dir: str) -> int:
        """
        CSVからインポート
        """
        pass
    
    def backup_database(self, backup_path: str):
        """
        データベース全体のバックアップ
        """
        pass
```

## 受け入れ条件
- [ ] SQLiteデータベースの自動初期化
- [ ] 結果の完全な保存（メトリクス、取引、設定）
- [ ] 高速な検索とフィルタリング
- [ ] データ整合性の保証（トランザクション）
- [ ] 既存結果の上書き防止
- [ ] エクスポート/インポート機能
- [ ] パフォーマンス（1000件以上の結果でも高速）

## 依存関係
- sqlite3（標準ライブラリ）
- pandas（データ操作）
- pyarrow（Parquetサポート、オプション）

## タスク
- [ ] データベーススキーマの作成
- [ ] BacktestRepositoryクラスの実装
- [ ] CRUD操作の実装
- [ ] 検索・フィルタリング機能
- [ ] トランザクション管理
- [ ] Parquetサポート（オプション）
- [ ] データ移行ツール
- [ ] インデックス最適化
- [ ] 統合テスト作成