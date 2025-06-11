# Private ISU v2 本番環境セットアップガイド

## 🚀 概要

Private ISU v2は、FastAPI + Redis + aiomysqlを使用した高性能なWebアプリケーションです。
本番環境では **Dockerを使用せず**、直接システムにインストールされたサービスを使用します。

## 📋 システム要件

### 必須サービス
- **Python 3.13+** (uvパッケージマネージャー推奨)
- **MySQL 8.0+** 
- **Redis 7.0+**
- **Nginx 1.18+**

### 推奨スペック
- **CPU**: 2コア以上
- **メモリ**: 4GB以上
- **ディスク**: 20GB以上の空き容量

## 🛠️ セットアップ手順

### 1. システム依存関係のインストール

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3-pip python3-venv mysql-server redis-server nginx curl

# uvインストール（推奨）
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env
```

### 2. MySQL設定

```bash
# MySQL起動・有効化
sudo systemctl start mysql
sudo systemctl enable mysql

# データベース作成（既存の場合はスキップ）
sudo mysql -e "CREATE DATABASE IF NOT EXISTS isuconp;"
sudo mysql -e "CREATE USER IF NOT EXISTS 'isucon'@'localhost' IDENTIFIED BY 'password';"
sudo mysql -e "GRANT ALL PRIVILEGES ON isuconp.* TO 'isucon'@'localhost';"
sudo mysql -e "FLUSH PRIVILEGES;"
```

### 3. Redis設定

```bash
# Redis起動・有効化
sudo systemctl start redis-server
sudo systemctl enable redis-server

# 設定確認
redis-cli ping  # "PONG"が返ってくることを確認
```

### 4. アプリケーションデプロイ

```bash
# アプリケーションディレクトリに移動
cd /home/isucon/private_isu/webapp/python

# 環境変数設定（必要に応じて調整）
export ISUCONP_DB_HOST=localhost
export ISUCONP_DB_USER=isucon
export ISUCONP_DB_PASSWORD=password
export ISUCONP_DB_NAME=isuconp

# 本番環境起動
./start_production.sh
```

## 🔧 systemdサービス設定（オプション）

アプリケーションをシステムサービスとして管理する場合：

```bash
# サービスファイルをコピー
sudo cp private-isu.service /etc/systemd/system/

# サービス有効化・起動
sudo systemctl daemon-reload
sudo systemctl enable private-isu
sudo systemctl start private-isu

# ステータス確認
sudo systemctl status private-isu
```

## 📊 動作確認

### ヘルスチェック

```bash
# アプリケーション直接アクセス
curl http://localhost:8080/health

# Nginx経由アクセス
curl http://localhost/health

# Webブラウザでアクセス
http://your-server-ip/
```

### パフォーマンス監視

```bash
# Redis統計
redis-cli info stats

# MySQL プロセス確認
mysqladmin processlist

# Nginx統計（localhost限定）
curl http://localhost/nginx_status

# アプリケーションログ
tail -f /home/isucon/private_isu/webapp/python/app.log

# システムログ
sudo journalctl -u private-isu -f
```

## 🔧 運用コマンド

### アプリケーション管理

```bash
# 再起動
./start_production.sh

# 停止
pkill -f "uvicorn.*app:app"

# ログ確認
tail -f app.log
```

### systemdサービス使用時

```bash
# 再起動
sudo systemctl restart private-isu

# 停止
sudo systemctl stop private-isu

# ログ確認
sudo journalctl -u private-isu -f
```

### Nginx管理

```bash
# 設定テスト
sudo nginx -t

# 再読み込み
sudo systemctl reload nginx

# 再起動
sudo systemctl restart nginx
```

## 🚨 トラブルシューティング

### アプリケーションが起動しない

1. **依存関係確認**
   ```bash
   cd /home/isucon/private_isu/webapp/python
   uv sync
   ```

2. **環境変数確認**
   ```bash
   echo $ISUCONP_DB_HOST
   echo $REDIS_HOST
   ```

3. **サービス状態確認**
   ```bash
   sudo systemctl status mysql redis-server nginx
   ```

### データベース接続エラー

1. **MySQL接続テスト**
   ```bash
   mysql -h localhost -u isucon -p isuconp
   ```

2. **設定確認**
   ```bash
   sudo mysql -e "SHOW GRANTS FOR 'isucon'@'localhost';"
   ```

### Redis接続エラー

1. **Redis接続テスト**
   ```bash
   redis-cli ping
   ```

2. **設定確認**
   ```bash
   sudo systemctl status redis-server
   ```

### Nginx設定エラー

1. **設定テスト**
   ```bash
   sudo nginx -t
   ```

2. **ログ確認**
   ```bash
   sudo tail -f /var/log/nginx/error.log
   ```

## 📈 パフォーマンス最適化

### データベース最適化

- インデックスは自動作成されます
- 必要に応じて `my.cnf` を調整

### Redis最適化

```bash
# Redis設定例 (/etc/redis/redis.conf)
maxmemory 1gb
maxmemory-policy allkeys-lru
```

### Nginx最適化

```bash
# worker_processes auto
# worker_connections 1024
```

## 🔒 セキュリティ設定

### ファイアウォール

```bash
# UFW使用例
sudo ufw allow 22    # SSH
sudo ufw allow 80    # HTTP
sudo ufw allow 443   # HTTPS
sudo ufw enable
```

### ログローテーション

```bash
# logrotate設定例
sudo vim /etc/logrotate.d/private-isu
```

## 📞 サポート

問題が発生した場合は、以下の情報を確認してください：

1. アプリケーションログ: `tail -f app.log`
2. システムログ: `sudo journalctl -u private-isu`
3. Nginxログ: `sudo tail -f /var/log/nginx/error.log`
4. システム状態: `sudo systemctl status mysql redis-server nginx`

---

**🎉 Private ISU v2で高性能なWebアプリケーションをお楽しみください！** 