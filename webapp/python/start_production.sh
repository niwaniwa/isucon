#!/bin/bash

# Private ISU Python v2 - 本番環境起動スクリプト（Docker非使用）

set -e

echo "🚀 Private ISU v2 Production Setup Starting..."

# 現在のディレクトリ確認
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# ユーザー確認
if [ "$EUID" -eq 0 ]; then
  echo "❌ このスクリプトはrootユーザーで実行しないでください"
  exit 1
fi

echo "📦 Installing Python dependencies..."
uv sync --quiet

echo "🔧 Checking system dependencies..."

# Redis設定確認
if ! systemctl is-active --quiet redis-server; then
    echo "⚠️  Redis is not running. Starting Redis..."
    sudo systemctl start redis-server
    sudo systemctl enable redis-server
fi

# MySQL設定確認  
if ! systemctl is-active --quiet mysql; then
    echo "⚠️  MySQL is not running. Starting MySQL..."
    sudo systemctl start mysql
    sudo systemctl enable mysql
fi

echo "📁 Creating image storage directory..."
sudo mkdir -p /var/www/images
sudo chown -R $USER:$USER /var/www/images
sudo chmod -R 755 /var/www/images

echo "🔧 Setting up environment variables..."
export ISUCONP_DB_HOST=${ISUCONP_DB_HOST:-localhost}
export ISUCONP_DB_PORT=${ISUCONP_DB_PORT:-3306}
export ISUCONP_DB_USER=${ISUCONP_DB_USER:-root}
export ISUCONP_DB_PASSWORD=${ISUCONP_DB_PASSWORD:-}
export ISUCONP_DB_NAME=${ISUCONP_DB_NAME:-isuconp}
export REDIS_HOST=${REDIS_HOST:-localhost}
export REDIS_PORT=${REDIS_PORT:-6379}
export REDIS_DB=${REDIS_DB:-0}

echo "🌐 Setting up Nginx configuration..."
if [ -f "/etc/nginx/sites-available/private-isu" ]; then
    echo "  - Nginx configuration already exists"
else
    echo "  - Creating Nginx configuration..."
    sudo cp nginx-production.conf /etc/nginx/sites-available/private-isu
    sudo ln -sf /etc/nginx/sites-available/private-isu /etc/nginx/sites-enabled/private-isu
    sudo rm -f /etc/nginx/sites-enabled/default
fi

echo "🔍 Testing Nginx configuration..."
sudo nginx -t

echo "🔄 Reloading Nginx..."
sudo systemctl reload nginx
sudo systemctl enable nginx

echo "🎯 Starting Private ISU application..."

# 既存のプロセスを停止
if pgrep -f "uvicorn.*app:app" > /dev/null; then
    echo "  - Stopping existing application..."
    pkill -f "uvicorn.*app:app" || true
    sleep 2
fi

# アプリケーション起動
echo "  - Starting new application..."
nohup .venv/bin/uvicorn app:app --host 0.0.0.0 --port 8080 --workers 4 > app.log 2>&1 &
APP_PID=$!

echo "⏱️  Waiting for application to start..."
sleep 5

# ヘルスチェック
if curl -s http://localhost:8080/health > /dev/null 2>&1; then
    echo "  ✅ Application health check: OK"
else
    echo "  ❌ Application health check: FAILED"
    echo "  Check logs: tail -f app.log"
    exit 1
fi

# Nginxプロキシ経由のチェック
if curl -s http://localhost/health > /dev/null 2>&1; then
    echo "  ✅ Nginx proxy check: OK"
else
    echo "  ❌ Nginx proxy check: FAILED"
    echo "  Check Nginx logs: sudo tail -f /var/log/nginx/error.log"
fi

echo ""
echo "🎉 Private ISU v2 Production Setup Complete!"
echo ""
echo "📊 Service Status:"
echo "  - Application PID: $APP_PID"
echo "  - Application logs: tail -f $SCRIPT_DIR/app.log"
echo "  - Nginx status: sudo systemctl status nginx"
echo "  - Redis status: sudo systemctl status redis-server"  
echo "  - MySQL status: sudo systemctl status mysql"
echo ""
echo "📋 Access Points:"
echo "  - Main Application: http://localhost/ (or your server IP)"
echo "  - Health Check: http://localhost/health"
echo "  - Direct App Port: http://localhost:8080/health"
echo ""
echo "🔧 Management Commands:"
echo "  - Stop app: pkill -f 'uvicorn.*app:app'"
echo "  - View logs: tail -f app.log"
echo "  - Restart app: ./start_production.sh"
echo "  - Restart Nginx: sudo systemctl restart nginx"
echo ""
echo "💾 Performance Monitoring:"
echo "  - Redis stats: redis-cli info stats"
echo "  - MySQL process: mysqladmin processlist"
echo "  - Disk usage: df -h /var/www/images"
echo "" 