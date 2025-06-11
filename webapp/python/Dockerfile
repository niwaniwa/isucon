FROM ghcr.io/astral-sh/uv:python3.13-bookworm

RUN \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \
  --mount=type=cache,target=/var/cache/apt,sharing=locked \
  apt-get update -qq && apt-get install -y build-essential default-libmysqlclient-dev openssl curl

RUN mkdir -p /home/webapp
WORKDIR /home/webapp

COPY pyproject.toml uv.lock .
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --compile-bytecode
COPY . .

# 画像保存ディレクトリ作成
RUN mkdir -p /var/www/images && chmod 755 /var/www/images

# 実行権限を付与
RUN chmod +x start_production.sh start_v2.sh

# 本番環境用の設定ファイルを適切な場所に配置
RUN mkdir -p /etc/nginx/sites-available /etc/systemd/system

# 環境変数による起動モード選択
ENV DEPLOYMENT_MODE=docker

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# 起動コマンド (Docker環境用、FastAPI v2アプリケーション)
ENTRYPOINT [ "/home/webapp/.venv/bin/uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "4" ]
