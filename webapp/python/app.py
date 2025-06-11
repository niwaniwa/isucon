import asyncio
import datetime
import hashlib
import os
import re
import shlex
import subprocess
import tempfile
from typing import Optional, List, Dict, Any
from functools import lru_cache

import aiomysql
import aiofiles
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, Depends, Request, Form, File, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Constants
UPLOAD_LIMIT = 10 * 1024 * 1024  # 10mb
POSTS_PER_PAGE = 20
IMAGE_STORAGE_DIR = "/var/www/images"

# FastAPI app setup
app = FastAPI(title="Private ISU v2", version="2.0.0")
templates = Jinja2Templates(directory="templates")

# カスタムフィルタとグローバル関数を追加
def image_url_filter(post):
    """Template filter for image URL generation"""
    ext = ""
    if post["mime"] == "image/jpeg":
        ext = ".jpg"
    elif post["mime"] == "image/png":
        ext = ".png"
    elif post["mime"] == "image/gif":
        ext = ".gif"
    return f"/image/{post['id']}{ext}"

def nl2br_filter(value):
    """Template filter for newline to br conversion"""
    if not value:
        return ""
    # 改行を<br>タグに変換
    return value.replace('\n', '<br>')

# Jinja2環境のカスタマイズ
templates.env.globals['image_url'] = image_url_filter
templates.env.filters['nl2br'] = nl2br_filter

# Static files
app.mount("/css", StaticFiles(directory="../public/css"), name="css")
app.mount("/js", StaticFiles(directory="../public/js"), name="js")
app.mount("/img", StaticFiles(directory="../public/img"), name="img")

# Global connections
db_pool: Optional[aiomysql.Pool] = None
redis_client: Optional[redis.Redis] = None

# Pydantic models
class User(BaseModel):
    id: int
    account_name: str
    authority: int
    del_flg: int
    created_at: datetime.datetime

class Post(BaseModel):
    id: int
    user_id: int
    body: str
    mime: str
    created_at: datetime.datetime
    comment_count: int = 0
    comments: List[Dict[str, Any]] = []
    user: Optional[Dict[str, Any]] = None

class Comment(BaseModel):
    id: int
    post_id: int
    user_id: int
    comment: str
    created_at: datetime.datetime
    user: Optional[Dict[str, Any]] = None

# Configuration
@lru_cache()
def get_config():
    return {
        "db": {
            "host": os.environ.get("ISUCONP_DB_HOST", "localhost"),
            "port": int(os.environ.get("ISUCONP_DB_PORT", "3306")),
            "user": os.environ.get("ISUCONP_DB_USER", "root"),
            "password": os.environ.get("ISUCONP_DB_PASSWORD", ""),
            "db": os.environ.get("ISUCONP_DB_NAME", "isuconp"),
        },
        "redis": {
            "host": os.environ.get("REDIS_HOST", "localhost"),
            "port": int(os.environ.get("REDIS_PORT", "6379")),
            "db": int(os.environ.get("REDIS_DB", "0")),
        }
    }

# Database connection
async def get_db_pool():
    global db_pool
    if db_pool is None:
        config = get_config()["db"]
        db_pool = await aiomysql.create_pool(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            db=config["db"],
            charset="utf8mb4",
            autocommit=True,
            maxsize=20,
            minsize=5,
        )
    return db_pool

async def get_db():
    pool = await get_db_pool()
    return pool

# Redis connection
async def get_redis():
    global redis_client
    if redis_client is None:
        config = get_config()["redis"]
        redis_client = redis.Redis(
            host=config["host"],
            port=config["port"],
            db=config["db"],
            decode_responses=True
        )
    return redis_client

# Utility functions
def digest(src: str) -> str:
    """Calculate SHA512 digest using openssl"""
    out = subprocess.check_output(
        f"printf %s {shlex.quote(src)} | openssl dgst -sha512 | sed 's/^.*= //'",
        shell=True,
        encoding="utf-8",
    )
    return out.strip()

def calculate_salt(account_name: str) -> str:
    return digest(account_name)

def calculate_passhash(account_name: str, password: str) -> str:
    return digest(f"{password}:{calculate_salt(account_name)}")

def validate_user(account_name: str, password: str) -> bool:
    if not re.match(r"[0-9a-zA-Z_]{3,}", account_name):
        return False
    if not re.match(r"[0-9a-zA-Z_]{6,}", password):
        return False
    return True

def image_url(post_id: int, mime: str) -> str:
    ext = ""
    if mime == "image/jpeg":
        ext = ".jpg"
    elif mime == "image/png":
        ext = ".png"
    elif mime == "image/gif":
        ext = ".gif"
    return f"/image/{post_id}{ext}"

async def save_image_to_file(post_id: int, imgdata: bytes, mime: str):
    """画像をファイルシステムに保存"""
    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif"}
    ext = ext_map.get(mime)
    if not ext:
        return None
    
    # ディレクトリが存在しない場合は作成
    os.makedirs(IMAGE_STORAGE_DIR, exist_ok=True)
    
    file_path = f"{IMAGE_STORAGE_DIR}/{post_id}.{ext}"
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(imgdata)
    return file_path

# Session management (simplified - using Redis)
async def get_session_user(request: Request) -> Optional[Dict[str, Any]]:
    session_id = request.cookies.get("session_id")
    if not session_id:
        return None
    
    redis_conn = await get_redis()
    user_data = await redis_conn.hgetall(f"session:{session_id}")
    if not user_data:
        return None
    
    # Get user from database
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT * FROM users WHERE id = %s", (user_data["user_id"],))
            return await cursor.fetchone()

async def create_session(user_id: int) -> str:
    """Create a new session"""
    import secrets
    session_id = secrets.token_urlsafe(32)
    
    redis_conn = await get_redis()
    await redis_conn.hset(f"session:{session_id}", mapping={
        "user_id": user_id,
        "csrf_token": secrets.token_urlsafe(16)
    })
    await redis_conn.expire(f"session:{session_id}", 3600 * 24)  # 24 hours
    
    return session_id

# Database operations with caching
async def try_login(account_name: str, password: str) -> Optional[Dict[str, Any]]:
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                "SELECT * FROM users WHERE account_name = %s AND del_flg = 0",
                (account_name,)
            )
            user = await cursor.fetchone()
            
            if user and calculate_passhash(user["account_name"], password) == user["passhash"]:
                return user
            return None

async def get_posts_with_cache(limit: int = POSTS_PER_PAGE * 2) -> List[Dict[str, Any]]:
    """投稿一覧を取得（キャッシュ付き）"""
    redis_conn = await get_redis()
    cache_key = f"posts:latest:{limit}"
    
    # キャッシュから取得を試行
    cached_posts = await redis_conn.get(cache_key)
    if cached_posts:
        import json
        return json.loads(cached_posts)
    
    # DBから取得
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                "SELECT id, user_id, body, created_at, mime FROM posts ORDER BY created_at DESC LIMIT %s",
                (limit,)
            )
            posts = await cursor.fetchall()
            
            # Convert datetime to string for JSON serialization
            for post in posts:
                post["created_at"] = post["created_at"].isoformat()
            
            # キャッシュに保存（60秒TTL）
            import json
            await redis_conn.setex(cache_key, 60, json.dumps(posts, default=str))
            
            return posts

async def make_posts_optimized(results: List[Dict[str, Any]], all_comments: bool = False) -> List[Dict[str, Any]]:
    """最適化された投稿データ作成"""
    if not results:
        return []
    
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            post_ids = [post["id"] for post in results]
            user_ids = list(set(post["user_id"] for post in results))
            
            # 一括でコメント数を取得
            await cursor.execute(
                "SELECT post_id, COUNT(*) as count FROM comments WHERE post_id IN %s GROUP BY post_id",
                (post_ids,)
            )
            comment_counts = {row["post_id"]: row["count"] for row in await cursor.fetchall()}
            
            # 一括でコメントを取得
            if all_comments:
                await cursor.execute("""
                    SELECT c.*, u.id as comment_user_id, u.account_name as comment_user_account_name, 
                           u.del_flg as comment_user_del_flg, u.authority as comment_user_authority,
                           u.created_at as comment_user_created_at, u.passhash as comment_user_passhash
                    FROM comments c 
                    JOIN users u ON c.user_id = u.id 
                    WHERE c.post_id IN %s 
                    ORDER BY c.post_id, c.created_at DESC
                """, (post_ids,))
            else:
                await cursor.execute("""
                    SELECT c.*, u.id as comment_user_id, u.account_name as comment_user_account_name, 
                           u.del_flg as comment_user_del_flg, u.authority as comment_user_authority,
                           u.created_at as comment_user_created_at, u.passhash as comment_user_passhash
                    FROM (
                        SELECT c1.*, ROW_NUMBER() OVER (PARTITION BY c1.post_id ORDER BY c1.created_at DESC) as rn
                        FROM comments c1
                        WHERE c1.post_id IN %s
                    ) c
                    JOIN users u ON c.user_id = u.id 
                    WHERE c.rn <= 3
                    ORDER BY c.post_id, c.created_at DESC
                """, (post_ids,))
            
            # コメントデータをグループ化
            comments_by_post = {}
            for row in await cursor.fetchall():
                post_id = row["post_id"]
                if post_id not in comments_by_post:
                    comments_by_post[post_id] = []
                
                comment_user = {
                    "id": row["comment_user_id"],
                    "account_name": row["comment_user_account_name"],
                    "del_flg": row["comment_user_del_flg"],
                    "authority": row["comment_user_authority"],
                    "created_at": row["comment_user_created_at"],
                    "passhash": row["comment_user_passhash"]
                }
                
                comment = {
                    "id": row["id"],
                    "post_id": row["post_id"],
                    "user_id": row["user_id"],
                    "comment": row["comment"],
                    "created_at": row["created_at"],
                    "user": comment_user
                }
                comments_by_post[post_id].append(comment)
            
            # 一括でユーザー情報を取得
            await cursor.execute("SELECT * FROM users WHERE id IN %s", (user_ids,))
            users_by_id = {user["id"]: user for user in await cursor.fetchall()}
            
            # データを組み立て
            posts = []
            for post in results:
                # Convert datetime string back to datetime if needed
                if isinstance(post["created_at"], str):
                    post["created_at"] = datetime.datetime.fromisoformat(post["created_at"])
                
                post["comment_count"] = comment_counts.get(post["id"], 0)
                post_comments = comments_by_post.get(post["id"], [])
                post_comments.reverse()  # 古い順に並び替え
                post["comments"] = post_comments
                post["user"] = users_by_id.get(post["user_id"])
                
                if post["user"] and not post["user"]["del_flg"]:
                    posts.append(post)
                
                if len(posts) >= POSTS_PER_PAGE:
                    break
            
            return posts

# 追加エンドポイントとキャッシュ戦略

async def get_user_with_cache(account_name: str) -> Optional[Dict[str, Any]]:
    """ユーザー情報をキャッシュ付きで取得"""
    redis_conn = await get_redis()
    cache_key = f"user:{account_name}"
    
    # キャッシュから取得を試行
    cached_user = await redis_conn.get(cache_key)
    if cached_user:
        import json
        return json.loads(cached_user)
    
    # DBから取得
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                "SELECT * FROM users WHERE account_name = %s AND del_flg = 0",
                (account_name,)
            )
            user = await cursor.fetchone()
            
            if user:
                # Convert datetime to string for JSON serialization
                user["created_at"] = user["created_at"].isoformat()
                
                # キャッシュに保存（300秒TTL）
                import json
                await redis_conn.setex(cache_key, 300, json.dumps(user, default=str))
            
            return user

async def invalidate_cache_on_post_create():
    """投稿作成時のキャッシュ無効化"""
    redis_conn = await get_redis()
    # 投稿一覧のキャッシュを削除
    await redis_conn.delete(f"posts:latest:{POSTS_PER_PAGE * 2}")

async def invalidate_cache_on_comment_create(post_id: int):
    """コメント作成時のキャッシュ無効化"""
    redis_conn = await get_redis()
    # 投稿詳細のキャッシュを削除
    await redis_conn.delete(f"post:{post_id}")
    # 投稿一覧のキャッシュも削除（コメント数が変わるため）
    await redis_conn.delete(f"posts:latest:{POSTS_PER_PAGE * 2}")

# API Endpoints

@app.get("/initialize")
async def initialize():
    """データベース初期化"""
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            sqls = [
                "DELETE FROM users WHERE id > 1000",
                "DELETE FROM posts WHERE id > 10000", 
                "DELETE FROM comments WHERE id > 100000",
                "UPDATE users SET del_flg = 0",
                "UPDATE users SET del_flg = 1 WHERE id % 50 = 0",
            ]
            for sql in sqls:
                await cursor.execute(sql)
            
            # インデックス作成
            index_sqls = [
                "CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts (created_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_posts_user_id ON posts (user_id)",
                "CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments (post_id)",
                "CREATE INDEX IF NOT EXISTS idx_comments_user_id ON comments (user_id)",
                "CREATE INDEX IF NOT EXISTS idx_users_del_flg ON users (del_flg)",
                "CREATE INDEX IF NOT EXISTS idx_posts_user_created ON posts (user_id, created_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_comments_post_created ON comments (post_id, created_at DESC)",
            ]
            for sql in index_sqls:
                try:
                    await cursor.execute(sql)
                except Exception:
                    pass  # インデックスが既に存在する場合は無視
    
    # キャッシュクリア
    redis_conn = await get_redis()
    await redis_conn.flushdb()
    
    return ""

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    """メインページ"""
    me = await get_session_user(request)
    posts_data = await get_posts_with_cache()
    posts = await make_posts_optimized(posts_data)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "posts": posts,
        "me": me
    })

@app.get("/login", response_class=HTMLResponse)
async def get_login(request: Request):
    """ログインページ"""
    if await get_session_user(request):
        return RedirectResponse(url="/", status_code=302)
    
    return templates.TemplateResponse("login.html", {
        "request": request,
        "me": None
    })

@app.post("/login")
async def post_login(
    request: Request,
    account_name: str = Form(...),
    password: str = Form(...)
):
    """ログイン処理"""
    if await get_session_user(request):
        return RedirectResponse(url="/", status_code=302)
    
    user = await try_login(account_name, password)
    if user:
        session_id = await create_session(user["id"])
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie("session_id", session_id, httponly=True, max_age=86400)
        return response
    
    return RedirectResponse(url="/login?error=1", status_code=302)

@app.get("/register", response_class=HTMLResponse)
async def get_register(request: Request):
    """登録ページ"""
    if await get_session_user(request):
        return RedirectResponse(url="/", status_code=302)
    
    return templates.TemplateResponse("register.html", {
        "request": request,
        "me": None
    })

@app.post("/register")
async def post_register(
    request: Request,
    account_name: str = Form(...),
    password: str = Form(...)
):
    """ユーザー登録"""
    if await get_session_user(request):
        return RedirectResponse(url="/", status_code=302)
    
    if not validate_user(account_name, password):
        return RedirectResponse(url="/register?error=validation", status_code=302)
    
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # 既存ユーザーチェック
            await cursor.execute("SELECT 1 FROM users WHERE account_name = %s", (account_name,))
            if await cursor.fetchone():
                return RedirectResponse(url="/register?error=exists", status_code=302)
            
            # ユーザー作成
            await cursor.execute(
                "INSERT INTO users (account_name, passhash) VALUES (%s, %s)",
                (account_name, calculate_passhash(account_name, password))
            )
            user_id = conn.insert_id()
            
            # セッション作成
            session_id = await create_session(user_id)
            response = RedirectResponse(url="/", status_code=302)
            response.set_cookie("session_id", session_id, httponly=True, max_age=86400)
            return response

@app.get("/logout")
async def get_logout(request: Request):
    """ログアウト"""
    session_id = request.cookies.get("session_id")
    if session_id:
        redis_conn = await get_redis()
        await redis_conn.delete(f"session:{session_id}")
    
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("session_id")
    return response

@app.get("/image/{post_id}.{ext}")
async def get_image(post_id: int, ext: str):
    """画像配信（最適化版）"""
    # まずファイルシステムから配信を試行
    file_path = f"{IMAGE_STORAGE_DIR}/{post_id}.{ext}"
    if os.path.exists(file_path):
        return FileResponse(file_path)
    
    # ファイルが存在しない場合はDBから取得
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT * FROM posts WHERE id = %s", (post_id,))
            post = await cursor.fetchone()
            
            if not post:
                raise HTTPException(status_code=404, detail="Post not found")
            
            # MIMEタイプチェック
            mime_ext_map = {
                "image/jpeg": "jpg",
                "image/png": "png", 
                "image/gif": "gif"
            }
            
            if ext not in mime_ext_map.values() or mime_ext_map.get(post["mime"]) != ext:
                raise HTTPException(status_code=404, detail="Invalid image format")
            
            # ファイルシステムに保存（次回用）
            await save_image_to_file(post_id, post["imgdata"], post["mime"])
            
            # レスポンス返却
            return Response(content=post["imgdata"], media_type=post["mime"])

@app.get("/@{account_name}", response_class=HTMLResponse)
async def get_user_profile(request: Request, account_name: str):
    """ユーザープロフィールページ"""
    me = await get_session_user(request)
    
    user = await get_user_with_cache(account_name)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Convert datetime string back to datetime if needed
    if isinstance(user["created_at"], str):
        user["created_at"] = datetime.datetime.fromisoformat(user["created_at"])
    
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # ユーザーの投稿を取得
            await cursor.execute(
                "SELECT id, user_id, body, mime, created_at FROM posts WHERE user_id = %s ORDER BY created_at DESC",
                (user["id"],)
            )
            posts_data = await cursor.fetchall()
            posts = await make_posts_optimized(posts_data)
            
            # 統計情報を取得
            await cursor.execute(
                "SELECT COUNT(*) AS count FROM comments WHERE user_id = %s",
                (user["id"],)
            )
            comment_count = (await cursor.fetchone())["count"]
            
            await cursor.execute(
                "SELECT id FROM posts WHERE user_id = %s",
                (user["id"],)
            )
            post_ids = [p["id"] for p in await cursor.fetchall()]
            post_count = len(post_ids)
            
            commented_count = 0
            if post_count > 0:
                await cursor.execute(
                    "SELECT COUNT(*) AS count FROM comments WHERE post_id IN %s",
                    (post_ids,)
                )
                commented_count = (await cursor.fetchone())["count"]
    
    return templates.TemplateResponse("user.html", {
        "request": request,
        "posts": posts,
        "user": user,
        "post_count": post_count,
        "comment_count": comment_count,
        "commented_count": commented_count,
        "me": me
    })

@app.get("/posts", response_class=HTMLResponse)
async def get_posts(request: Request, max_created_at: Optional[str] = None):
    """投稿一覧ページ（ページング対応）"""
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            if max_created_at:
                # datetime文字列をパース
                import re
                m = re.match(r"(\d{4})-(\d{2})-(\d{2})[ tT](\d{2}):(\d{2}):(\d{2}).*", max_created_at)
                if m:
                    max_dt = datetime.datetime(*map(int, m.groups()))
                    await cursor.execute(
                        "SELECT id, user_id, body, mime, created_at FROM posts WHERE created_at <= %s ORDER BY created_at DESC LIMIT %s",
                        (max_dt, POSTS_PER_PAGE * 2)
                    )
                else:
                    await cursor.execute(
                        "SELECT id, user_id, body, mime, created_at FROM posts ORDER BY created_at DESC LIMIT %s",
                        (POSTS_PER_PAGE * 2,)
                    )
            else:
                await cursor.execute(
                    "SELECT id, user_id, body, mime, created_at FROM posts ORDER BY created_at DESC LIMIT %s",
                    (POSTS_PER_PAGE * 2,)
                )
            
            posts_data = await cursor.fetchall()
            posts = await make_posts_optimized(posts_data)
    
    return templates.TemplateResponse("posts.html", {
        "request": request,
        "posts": posts
    })

@app.get("/posts/{post_id}", response_class=HTMLResponse)
async def get_post_detail(request: Request, post_id: int):
    """投稿詳細ページ"""
    me = await get_session_user(request)
    
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT * FROM posts WHERE id = %s", (post_id,))
            post_data = await cursor.fetchall()
            
            if not post_data:
                raise HTTPException(status_code=404, detail="Post not found")
            
            posts = await make_posts_optimized(post_data, all_comments=True)
            if not posts:
                raise HTTPException(status_code=404, detail="Post not found")
    
    return templates.TemplateResponse("post.html", {
        "request": request,
        "post": posts[0],
        "me": me
    })

@app.post("/")
async def create_post(
    request: Request,
    csrf_token: str = Form(...),
    body: str = Form(...),
    file: UploadFile = File(...)
):
    """投稿作成"""
    me = await get_session_user(request)
    if not me:
        return RedirectResponse(url="/login", status_code=302)
    
    # CSRF トークン検証（簡易版）
    session_id = request.cookies.get("session_id")
    if session_id:
        redis_conn = await get_redis()
        session_data = await redis_conn.hgetall(f"session:{session_id}")
        if session_data.get("csrf_token") != csrf_token:
            raise HTTPException(status_code=422, detail="Invalid CSRF token")
    
    # ファイル検証
    if not file or file.filename == "":
        return RedirectResponse(url="/?error=no_file", status_code=302)
    
    # MIMEタイプ検証
    if file.content_type not in ("image/jpeg", "image/png", "image/gif"):
        return RedirectResponse(url="/?error=invalid_format", status_code=302)
    
    # ファイルサイズ検証
    file_content = await file.read()
    if len(file_content) > UPLOAD_LIMIT:
        return RedirectResponse(url="/?error=file_too_large", status_code=302)
    
    # DBに保存
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "INSERT INTO posts (user_id, mime, imgdata, body) VALUES (%s, %s, %s, %s)",
                (me["id"], file.content_type, file_content, body)
            )
            post_id = conn.insert_id()
            
            # ファイルシステムにも保存
            await save_image_to_file(post_id, file_content, file.content_type)
            
            # キャッシュ無効化
            await invalidate_cache_on_post_create()
    
    return RedirectResponse(url=f"/posts/{post_id}", status_code=302)

@app.post("/comment")
async def create_comment(
    request: Request,
    csrf_token: str = Form(...),
    post_id: int = Form(...),
    comment: str = Form(...)
):
    """コメント作成"""
    me = await get_session_user(request)
    if not me:
        return RedirectResponse(url="/login", status_code=302)
    
    # CSRF トークン検証
    session_id = request.cookies.get("session_id")
    if session_id:
        redis_conn = await get_redis()
        session_data = await redis_conn.hgetall(f"session:{session_id}")
        if session_data.get("csrf_token") != csrf_token:
            raise HTTPException(status_code=422, detail="Invalid CSRF token")
    
    # コメント保存
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "INSERT INTO comments (post_id, user_id, comment) VALUES (%s, %s, %s)",
                (post_id, me["id"], comment)
            )
            
            # キャッシュ無効化
            await invalidate_cache_on_comment_create(post_id)
    
    return RedirectResponse(url=f"/posts/{post_id}", status_code=302)

@app.get("/admin/banned", response_class=HTMLResponse)
async def get_banned(request: Request):
    """BANページ"""
    me = await get_session_user(request)
    
    return templates.TemplateResponse("banned.html", {
        "request": request,
        "me": me
    })

@app.post("/admin/banned")
async def post_banned(
    request: Request,
    csrf_token: str = Form(...),
    uid: int = Form(...)
):
    """ユーザーBAN"""
    me = await get_session_user(request)
    if not me or me.get("authority") != 1:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    # CSRF トークン検証
    session_id = request.cookies.get("session_id")
    if session_id:
        redis_conn = await get_redis()
        session_data = await redis_conn.hgetall(f"session:{session_id}")
        if session_data.get("csrf_token") != csrf_token:
            raise HTTPException(status_code=422, detail="Invalid CSRF token")
    
    # ユーザーを削除フラグ設定
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("UPDATE users SET del_flg = 1 WHERE id = %s", (uid,))
            
            # ユーザーキャッシュを無効化
            await cursor.execute("SELECT account_name FROM users WHERE id = %s", (uid,))
            user = await cursor.fetchone()
            if user:
                redis_conn = await get_redis()
                await redis_conn.delete(f"user:{user['account_name']}")
    
    return RedirectResponse(url="/admin/banned", status_code=302)

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "2.0.0"}

# Startup event
@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時の初期化"""
    # Database pool initialization
    await get_db_pool()
    
    # Redis initialization
    await get_redis()
    
    # 画像保存ディレクトリ作成
    os.makedirs(IMAGE_STORAGE_DIR, exist_ok=True)

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=True)
