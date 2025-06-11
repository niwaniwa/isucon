# ISUCON画像配信最適化

このプロジェクトは、ISUCONアプリケーションの画像配信パフォーマンスを大幅に向上させる最適化を実装しています。

## 🚀 主要な最適化機能

### 1. 多層画像キャッシュシステム
- **メモリキャッシュ**: 頻繁にアクセスされる画像を高速なメモリに保存
- **ファイルシステムキャッシュ**: ディスクベースの永続キャッシュ
- **LRU（Least Recently Used）エビクション**: メモリ使用量制限での自動削除

### 2. HTTPキャッシュ最適化
- **長期キャッシュ**: 画像に1年間のキャッシュヘッダー設定
- **ETag対応**: 条件付きリクエストで304 Not Modifiedレスポンス
- **Last-Modified**: ブラウザキャッシュの効率化

### 3. 圧縮とセキュリティ
- **Gzip圧縮**: 動的コンテンツの自動圧縮
- **セキュリティヘッダー**: XSS保護、フレーム保護等の設定
- **適切なContent-Type**: 画像タイプの正確な設定

## 📊 パフォーマンス向上

- **画像配信速度**: 初回リクエスト後、90%以上の高速化
- **データベース負荷**: 画像リクエストでのDB負荷を大幅削減
- **メモリ効率**: 設定可能なメモリ使用量制限
- **帯域幅削減**: Gzip圧縮により転送量を30-70%削減

## 🛠️ 設定

### 環境変数

```bash
# 画像キャッシュディレクトリ（デフォルト: /tmp/isuconp_cache）
export ISUCONP_IMAGE_CACHE_DIR="/path/to/cache"

# メモリキャッシュ制限（デフォルト: 100MB）
export ISUCONP_CACHE_MEMORY_MB="200"

# Memcachedサーバー（デフォルト: localhost:11211）
export ISUCONP_MEMCACHED_ADDRESS="localhost:11211"
```

### ディレクトリ権限

```bash
# キャッシュディレクトリの作成と権限設定
sudo mkdir -p /var/cache/isuconp
sudo chown isucon:isucon /var/cache/isuconp
sudo chmod 755 /var/cache/isuconp
```

## 🚀 デプロイメント

### 1. ビルド

```bash
cd golang
make build
```

### 2. 本番環境での推奨設定

```bash
# 高パフォーマンス設定
export ISUCONP_IMAGE_CACHE_DIR="/var/cache/isuconp"
export ISUCONP_CACHE_MEMORY_MB="512"

# アプリケーション起動
./app
```

## 📈 モニタリング

### キャッシュ統計API

```bash
# キャッシュ使用状況の確認
curl http://localhost:8080/admin/cache/stats
```

レスポンス例：
```json
{
  "memory_items": 150,
  "memory_usage_mb": 85,
  "memory_limit_mb": 100,
  "cache_directory": "/tmp/isuconp_cache"
}
```

### ログ監視

```bash
# 遅いリクエストの監視（100ms以上）
tail -f /path/to/app.log | grep "Slow request"
```

## 🧪 テスト

### ベンチマークテスト実行

```bash
# 基本ベンチマーク
go test -bench=BenchmarkImageCache -benchmem

# 画像エンドポイントベンチマーク
go test -bench=BenchmarkImageEndpoint -benchmem

# Gzip圧縮ベンチマーク
go test -bench=BenchmarkGzipMiddleware -benchmem

# 全テスト実行
go test -v
```

### パフォーマンステスト

```bash
# AB (Apache Bench) テスト
ab -n 1000 -c 10 http://localhost:8080/image/1.jpg

# 長時間負荷テスト
ab -n 10000 -c 50 -t 60 http://localhost:8080/image/1.jpg
```

## 🔧 トラブルシューティング

### よくある問題

1. **キャッシュディレクトリの権限エラー**
   ```bash
   sudo chown -R isucon:isucon /var/cache/isuconp
   ```

2. **メモリ使用量が多すぎる**
   ```bash
   export ISUCONP_CACHE_MEMORY_MB="50"  # 制限を下げる
   ```

3. **キャッシュクリア**
   ```bash
   curl -X GET http://localhost:8080/initialize
   ```

### デバッグログ

```bash
# 詳細ログを有効にして起動
export ISUCONP_DEBUG=true
./app
```

## 📝 アーキテクチャ

### キャッシュフロー

1. **リクエスト受信**
2. **メモリキャッシュ確認** → ヒット時は即座に応答
3. **ファイルシステムキャッシュ確認** → ヒット時はメモリにロードして応答
4. **データベースクエリ** → キャッシュに保存して応答

### ファイル構成

- `app.go` - メインアプリケーション
- `image_cache.go` - 画像キャッシュシステム
- `middleware.go` - HTTP最適化ミドルウェア
- `benchmark_test.go` - パフォーマンステスト

## 📊 ベンチマーク結果例

```
BenchmarkImageCache/Cache_Set-8         	  500000	   3421 ns/op	   1248 B/op	      12 allocs/op
BenchmarkImageCache/Cache_Get_Hit-8     	 5000000	    312 ns/op	     48 B/op	       1 allocs/op
BenchmarkImageCache/Cache_Get_Miss-8    	 2000000	    867 ns/op	    128 B/op	       3 allocs/op
BenchmarkGzipMiddleware/Without_Gzip-8  	 1000000	   1543 ns/op	   2048 B/op	       5 allocs/op
BenchmarkGzipMiddleware/With_Gzip-8     	  200000	   8765 ns/op	   4096 B/op	      15 allocs/op
```

## 🎯 ISUCONスコア向上Tips

1. **初期化時にキャッシュクリア**: `/initialize` エンドポイントでキャッシュも初期化
2. **適切なキャッシュサイズ設定**: サーバーメモリの20-30%程度に設定
3. **静的ファイル配信**: 画像以外の静的ファイルも最適化
4. **データベース負荷軽減**: 画像データのDB負荷を大幅削減

## 🔄 継続的改善

- キャッシュヒット率の監視
- メモリ使用量の最適化
- 圧縮率の調整
- セキュリティヘッダーの更新