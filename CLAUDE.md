# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an ISUCON (Iikanjini Speed Up Contest) codebase for "Private ISU" - an Instagram-like social media application. The goal is to optimize the application to achieve the highest possible benchmark score.

## Architecture

### Application Structure
- **Current Implementation**: Go (webapp/golang/)
- **Other Available**: Ruby, PHP, Node.js, Python (in webapp/)
- **Database**: MySQL 8.4
- **Web Server**: Nginx (reverse proxy)

### Database Schema
- `users`: id, account_name, passhash, authority, del_flg, created_at
- `posts`: id, user_id, mime, imgdata, body, created_at
- `comments`: id, post_id, user_id, comment, created_at
- Key indexes already added on foreign keys and created_at columns


## Key Commands

### Development
```bash
# Start all services (from webapp/)
# First, update docker-compose.yml to use golang/ instead of python/
# Then run:
docker-compose up -d

# View logs
docker-compose logs -f app

# Restart application
docker-compose restart app

# Run benchmarker (from benchmarker/)
./run.sh
```

### Database
```bash
# Connect to MySQL
docker-compose exec mysql mysql -u root -proot isuconp

# Reset database
docker-compose exec mysql mysql -u root -proot -e "DROP DATABASE IF EXISTS isuconp; CREATE DATABASE isuconp;"
docker-compose exec mysql mysql -u root -proot isuconp < sql/schema.sql
```

### Go App Management
```bash
# Build Go app (from webapp/golang/)
make

# Access app container
docker-compose exec app bash

# View app logs
docker-compose logs -f app
```

## Scoring Rules

1. **Points**:
   - GET requests: 1 point
   - POST requests: 2 points
   - Image uploads: 5 points

2. **Penalties**:
   - Timeout (2s): -1 point
   - 4xx/5xx errors: -10 to -50 points
   - Wrong DOM structure: -100 points

3. **Requirements**:
   - Must pass all validation tests
   - Cannot modify benchmarker
   - Must maintain original functionality

## Critical Performance Areas

1. **Image Handling**: Images stored in DB as MEDIUMBLOB (potential optimization target)
2. **N+1 Queries**: Check for queries in loops
3. **Caching**: No caching layer implemented yet
4. **Database Indexes**: Basic indexes on foreign keys
5. **Connection Pooling**: Check DB connection settings

## Development Guidelines

### ISUCON Competition Rules Compliance (重要)

以下の項目は絶対に変更しないこと（public_manual.mdより）:
1. **アクセス先のURI**: ポート番号およびHTTPリクエストパスを変更禁止
2. **レスポンス(HTML)のDOM構造**: HTML構造を維持する必要がある
3. **JavaScript/CSSファイルの内容**: 変更禁止
4. **画像および動画等のメディアファイルの内容**: 変更禁止（保存場所の変更は可）

許可される最適化:
- DBスキーマの変更やインデックスの作成・削除
- キャッシュ機構の追加、jobqueue機構の追加による遅延書き込み
- 他の言語による再実装
- 画像の保存方法の変更（内容は変更不可）

### 最適化実施時の注意事項

1. **Before Optimizing**:
   - Run benchmarker to get baseline score
   - Check current bottlenecks in logs
   - Verify changes don't break functionality

2. **Testing Changes**:
   - Always run benchmarker after changes
   - Check docker-compose logs for errors
   - Verify DOM structure remains unchanged
   - POSTしたデータが即座にGETで取得できることを確認

3. **Common Optimization Targets**:
   - Query optimization (check slow query log)
   - Caching strategy improvements
   - Static file serving optimization
   - Application server tuning
   - Database parameter tuning

## Debugging

- **Benchmarker fails**: Check `docker-compose logs app`
- **Score drops**: Review recent changes, check for errors
- **Timeout errors**: Check slow queries, increase connection pool
- **Memory issues**: Monitor Redis memory usage

## Go Implementation Notes

- Uses standard net/http with gorilla/mux router
- Templates in webapp/golang/templates/
- Database driver: github.com/go-sql-driver/mysql
- Session management with gorilla/sessions