# チケット #001: TAFlowStrategy 実装

## 概要
TradingAgentsGraphをラップし、バックテスト用の戦略エンジンとして機能するTAFlowStrategyクラスの実装

## 目的
- 既存のTradingAgentsGraphを活用した売買判断の実行
- バックテスト環境での適切な動作（オフラインモード、キャッシュ利用）
- 日付を指定して Buy/Sell/Hold の判断を返すインターフェース

## 実装要件

### 1. クラス設計
```python
class TAFlowStrategy:
    def __init__(self, config: dict):
        """
        Args:
            config: TradingAgentsGraphの設定辞書
                    - online_tools: False固定（キャッシュのみ利用）
                    - その他既存のDEFAULT_CONFIG設定を継承
        """
        pass
    
    def decide(self, ticker: str, date: str) -> str:
        """
        指定日付での売買判断を返す
        
        Args:
            ticker: 銘柄シンボル（例: "AAPL"）
            date: 判断日（YYYY-MM-DD形式）
            
        Returns:
            "Buy" | "Sell" | "Hold" のいずれか
        """
        pass
```

### 2. 実装詳細
- TradingAgentsGraphのpropagateメソッドを内部で呼び出し
- エラーハンドリング（データ不足、API制限等）
- デバッグモードのサポート
- メモリ管理（results_dirへの保存）

### 3. 設定管理
- config["online_tools"] = False の強制
- キャッシュディレクトリの自動設定
- LLMモデル選択の柔軟性確保

## 受け入れ条件
- [ ] TAFlowStrategyクラスが実装され、decideメソッドが正しく動作する
- [ ] オフラインモードでのみ動作することが保証される
- [ ] エラー時の適切なフォールバック（例：データ不足時は"Hold"）
- [ ] ユニットテストの作成

## 依存関係
- tradingagents.graph.trading_graph
- tradingagents.default_config
- 既存のエージェント実装

## タスク
- [ ] TAFlowStrategyクラスの基本実装
- [ ] TradingAgentsGraphとの統合
- [ ] エラーハンドリングの実装
- [ ] 設定管理の実装
- [ ] ユニットテストの作成
- [ ] ドキュメント作成