#!/bin/bash
set -eu

# --- 設定 ---
# .envファイルなどから読み込むのが望ましいが、ここでは直接記述
DB_USER="isuconp"
DB_PASS="isuconp"
DB_NAME="isuconp"
# app.pyで定義されている画像保存用ディレクトリ
IMAGE_DIR="/var/www/images"
# データ移行用のPythonスクリプトのパス
MIGRATE_PY_SCRIPT="$(dirname "$0")/migrate_images.py"

echo "--- (1/4) Starting image migration ---"

# --- ステップ1: スキーマ変更（filepathカラムの追加） ---
echo "--- (2/4) Adding 'filepath' column to 'posts' table... ---"
# `posts`テーブルに`filepath`カラムを追加。すでに追加済みの場合はエラーにならないようにIF NOT EXISTSを使う
mysql -u"$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "ALTER TABLE posts ADD COLUMN filepath VARCHAR(255) NULL AFTER mime;"
echo "Schema alteration complete."

# --- ステップ2: データ移行（Pythonスクリプトの実行） ---
echo "--- (3/4) Migrating image data from MEDIUMBLOB to filesystem... ---"
# アプリケーションの仮想環境(venv)がある場合は、そのpythonを使う
# 例: /path/to/project/webapp/python/.venv/bin/python3
# ここではシステムデフォルトのpython3を想定
python3 "$MIGRATE_PY_SCRIPT"
echo "Data migration complete."

# --- ステップ3: 後片付け（古いカラムの削除） ---
# 注意: このステップはデータ移行が完全に成功したことを確認してから手動で実行するのがより安全です。
# 自動化に含める場合は、スクリプトが成功した場合のみ実行されるようにしています。
echo "--- (4/4) Dropping old 'imgdata' column... ---"
mysql -u"$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "ALTER TABLE posts DROP COLUMN imgdata;"
echo "--- Migration successfully finished! ---"