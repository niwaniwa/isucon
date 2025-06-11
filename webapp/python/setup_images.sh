#!/bin/bash

# 画像保存用ディレクトリの作成と権限設定
IMAGE_DIR="/var/www/images"

# ディレクトリを作成
sudo mkdir -p "$IMAGE_DIR"

# 権限を設定（Webサーバーが書き込み可能にする）
sudo chown -R www-data:www-data "$IMAGE_DIR"
sudo chmod -R 755 "$IMAGE_DIR"

echo "Image storage directory created at $IMAGE_DIR"
echo "Directory permissions set for web server access" 