# チケット #014: Redditテスト実装

## 概要
Reddit praw実装の包括的なテストスイートの実装

## 目的
- 各コンポーネントの単体テスト
- 統合テストの実装
- モックを使用したAPI呼び出しのテスト
- 既存システムとの互換性テスト

## 実装要件

### 1. テスト優先開発（TDD）アプローチ
```python
# テストを先に作成してから実装を行う
# 各モジュールの実装前にテストを定義
```

### 2. テスト構造
```
tests/
├── unit/
│   ├── test_reddit_praw_client.py
│   ├── test_reddit_data_fetcher.py
│   ├── test_reddit_cache_manager.py
│   └── test_reddit_utils_compatibility.py
├── integration/
│   ├── test_reddit_cli_commands.py
│   ├── test_reddit_full_flow.py
│   └── test_reddit_auto_update.py
├── fixtures/
│   ├── reddit_mock_data.py
│   └── reddit_test_config.py
└── conftest.py
```

### 3. RedditPrawClient テスト
```python
# tests/unit/test_reddit_praw_client.py

class TestRedditPrawClient:
    @pytest.fixture
    def mock_reddit(self):
        """prawのRedditオブジェクトをモック"""
        with patch('praw.Reddit') as mock:
            yield mock
    
    def test_authentication_success(self, mock_reddit):
        """認証成功のテスト"""
        client = RedditPrawClient(test_config)
        assert client.authenticate() is True
    
    def test_authentication_failure(self, mock_reddit):
        """認証失敗のテスト"""
        mock_reddit.side_effect = Exception("Invalid credentials")
        client = RedditPrawClient(invalid_config)
        assert client.authenticate() is False
    
    def test_get_subreddit_posts(self, mock_reddit):
        """subreddit投稿取得のテスト"""
        # モックデータ設定
        mock_posts = create_mock_posts(count=10)
        mock_reddit.return_value.subreddit.return_value.hot.return_value = mock_posts
        
        client = RedditPrawClient(test_config)
        posts = client.get_subreddit_posts("worldnews", limit=10)
        
        assert len(posts) == 10
        assert all('title' in post for post in posts)
```

### 4. RedditDataFetcher テスト
```python
# tests/unit/test_reddit_data_fetcher.py

class TestRedditDataFetcher:
    def test_fetch_global_news(self, mock_client):
        """グローバルニュース取得のテスト"""
        fetcher = RedditDataFetcher(mock_client, test_config)
        
        posts = fetcher.fetch_global_news("2024-01-01", limit_per_subreddit=5)
        
        # 5 subreddits × 5 posts = 25 posts expected
        assert len(posts) == 25
        assert all(post['posted_date'] == "2024-01-01" for post in posts)
    
    def test_company_news_filtering(self):
        """企業関連投稿のフィルタリングテスト"""
        posts = [
            {"title": "Apple announces new iPhone", "selftext": "..."},
            {"title": "Random tech news", "selftext": "..."},
            {"title": "AAPL stock rises", "selftext": "..."},
        ]
        
        filtered = filter_company_relevant_posts(posts, "AAPL", "Apple")
        assert len(filtered) == 2
    
    def test_duplicate_removal(self):
        """重複排除のテスト"""
        fetcher = RedditDataFetcher(mock_client, test_config)
        
        posts_with_duplicates = [
            {"id": "abc123", "title": "Post 1"},
            {"id": "def456", "title": "Post 2"},
            {"id": "abc123", "title": "Post 1"},  # 重複
        ]
        
        unique_posts = fetcher.remove_duplicates(posts_with_duplicates)
        assert len(unique_posts) == 2
```

### 5. RedditCacheManager テスト
```python
# tests/unit/test_reddit_cache_manager.py

class TestRedditCacheManager:
    @pytest.fixture
    def temp_cache_dir(self, tmp_path):
        """テスト用の一時ディレクトリ"""
        return tmp_path / "reddit_data"
    
    def test_save_and_load_posts(self, temp_cache_dir):
        """投稿の保存と読み込みテスト"""
        manager = RedditCacheManager(str(temp_cache_dir))
        
        test_posts = [
            {"id": "1", "title": "Test Post 1"},
            {"id": "2", "title": "Test Post 2"},
        ]
        
        # 保存
        file_path = manager.save_posts(
            test_posts, "global_news", "2024-01-01", "worldnews"
        )
        assert Path(file_path).exists()
        
        # 読み込み
        loaded_posts = manager.load_posts(
            "global_news", "2024-01-01", "worldnews"
        )
        assert len(loaded_posts) == 2
        assert loaded_posts[0]["title"] == "Test Post 1"
    
    def test_fetch_history_tracking(self, temp_cache_dir):
        """取得履歴の記録テスト"""
        manager = RedditCacheManager(str(temp_cache_dir))
        
        manager.update_fetch_history(
            "global_news",
            "2024-01-01",
            ["worldnews", "news"],
            "2024-01-02T10:00:00Z",
            100
        )
        
        history = manager.get_fetch_history()
        assert "global_news" in history
        assert history["global_news"]["2024-01-01"]["post_count"] == 100
```

### 6. 統合テスト
```python
# tests/integration/test_reddit_full_flow.py

@pytest.mark.integration
class TestRedditFullFlow:
    def test_end_to_end_data_fetch(self):
        """完全なデータ取得フローのテスト"""
        # 実際のAPIは使わず、モックで代替
        with patch('praw.Reddit') as mock_reddit:
            setup_mock_reddit_responses(mock_reddit)
            
            # CLI実行
            result = runner.invoke(cli, [
                'reddit', 'fetch-historical',
                '--no-interactive',
                '--start', '2024-01-01',
                '--end', '2024-01-01',
                '--category', 'global_news'
            ])
            
            assert result.exit_code == 0
            
            # データが保存されたか確認
            cache_manager = RedditCacheManager(test_data_dir)
            posts = cache_manager.load_posts("global_news", "2024-01-01")
            assert len(posts) > 0
```

### 7. モックデータ生成
```python
# tests/fixtures/reddit_mock_data.py

def create_mock_post(post_id: str = None, **kwargs):
    """モック投稿データの生成"""
    post = {
        "id": post_id or str(uuid.uuid4()),
        "title": kwargs.get("title", "Test Post Title"),
        "selftext": kwargs.get("selftext", "Test post content"),
        "url": kwargs.get("url", "https://reddit.com/test"),
        "ups": kwargs.get("ups", random.randint(1, 1000)),
        "created_utc": kwargs.get("created_utc", int(time.time())),
        "subreddit": kwargs.get("subreddit", "test"),
        "author": kwargs.get("author", "test_user"),
        "num_comments": kwargs.get("num_comments", random.randint(0, 100))
    }
    return post

def create_mock_posts(count: int = 10, **kwargs):
    """複数のモック投稿を生成"""
    return [create_mock_post(f"post_{i}", **kwargs) for i in range(count)]
```

### 8. 互換性テスト
```python
# tests/unit/test_reddit_utils_compatibility.py

class TestRedditUtilsCompatibility:
    def test_legacy_interface_maintained(self):
        """既存インターフェースが維持されているか"""
        # 既存の関数シグネチャでの呼び出し
        result = fetch_top_from_category(
            "global_news",
            "2024-01-01",
            100,
            data_path="test_data"
        )
        
        assert isinstance(result, list)
        assert all(isinstance(post, dict) for post in result)
    
    def test_data_format_conversion(self):
        """データ形式の変換テスト"""
        praw_posts = create_mock_posts(5)
        legacy_posts = convert_praw_to_legacy_format(praw_posts)
        
        # 既存形式のフィールドが存在するか
        for post in legacy_posts:
            assert "content" in post  # selftextから変換
            assert "upvotes" in post  # upsから変換
            assert "posted_date" in post  # created_utcから変換
```

### 9. パフォーマンステスト
```python
@pytest.mark.performance
def test_large_data_handling():
    """大量データ処理のパフォーマンステスト"""
    start_time = time.time()
    
    # 1000件のモックデータで処理
    large_dataset = create_mock_posts(1000)
    manager = RedditCacheManager(test_dir)
    manager.save_posts(large_dataset, "test", "2024-01-01")
    
    duration = time.time() - start_time
    assert duration < 5.0  # 5秒以内に完了
```

## 受け入れ条件
- [ ] テスト優先開発（TDD）の実践
- [ ] 全モジュールの単体テスト実装
- [ ] 統合テストの成功
- [ ] コードカバレッジ80%以上
- [ ] モックを使用したAPI非依存テスト
- [ ] 既存システムとの互換性確認
- [ ] パフォーマンステストの合格
- [ ] USE_PRAW_APIフラグのテスト

## 依存関係
- pytest
- pytest-mock
- pytest-cov
- 全Reddit実装モジュール

## タスク
- [ ] テストディレクトリ構造の作成
- [ ] モックデータ生成ユーティリティの作成
- [ ] RedditPrawClientのテスト作成
- [ ] RedditDataFetcherのテスト作成
- [ ] RedditCacheManagerのテスト作成
- [ ] CLIコマンドのテスト作成
- [ ] 統合テストの実装
- [ ] 互換性テスト
- [ ] 段階的実装フラグのテスト
- [ ] パフォーマンステスト
- [ ] CI/CD設定（GitHub Actions）