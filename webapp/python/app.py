import datetime
import os
import pathlib
import re
import shlex
import subprocess
import tempfile

import flask
import MySQLdb.cursors
from flask_session import Session
from jinja2 import pass_eval_context
from markupsafe import Markup, escape
from pymemcache.client.base import Client as MemcacheClient

UPLOAD_LIMIT = 10 * 1024 * 1024  # 10mb
POSTS_PER_PAGE = 20

# 画像保存用ディレクトリ
IMAGE_STORAGE_DIR = "/var/www/images"

_config = None


def config():
    global _config
    if _config is None:
        _config = {
            "db": {
                "host": os.environ.get("ISUCONP_DB_HOST", "localhost"),
                "port": int(os.environ.get("ISUCONP_DB_PORT", "3306")),
                "user": os.environ.get("ISUCONP_DB_USER", "root"),
                "db": os.environ.get("ISUCONP_DB_NAME", "isuconp"),
            },
            "memcache": {
                "address": os.environ.get(
                    "ISUCONP_MEMCACHED_ADDRESS", "127.0.0.1:11211"
                ),
            },
        }
        password = os.environ.get("ISUCONP_DB_PASSWORD")
        if password:
            _config["db"]["passwd"] = password
    return _config


_db = None


def db():
    global _db
    if _db is None:
        conf = config()["db"].copy()
        conf["charset"] = "utf8mb4"
        conf["cursorclass"] = MySQLdb.cursors.DictCursor
        conf["autocommit"] = True
        _db = MySQLdb.connect(**conf)
    return _db


def db_initialize():
    cur = db().cursor()
    sqls = [
        "DELETE FROM users WHERE id > 1000",
        "DELETE FROM posts WHERE id > 10000",
        "DELETE FROM comments WHERE id > 100000",
        "UPDATE users SET del_flg = 0",
        "UPDATE users SET del_flg = 1 WHERE id % 50 = 0",
    ]
    for q in sqls:
        cur.execute(q)
    
    # インデックスの作成（存在しない場合のみ）
    index_sqls = [
        "CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts (created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_posts_user_id ON posts (user_id)",
        "CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments (post_id)",
        "CREATE INDEX IF NOT EXISTS idx_comments_user_id ON comments (user_id)",
        "CREATE INDEX IF NOT EXISTS idx_users_del_flg ON users (del_flg)",
        "CREATE INDEX IF NOT EXISTS idx_posts_user_created ON posts (user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_comments_post_created ON comments (post_id, created_at DESC)",
    ]
    for q in index_sqls:
        try:
            cur.execute(q)
        except Exception as e:
            # インデックスが既に存在する場合などエラーを無視
            pass


_mcclient = None


def memcache():
    global _mcclient
    if _mcclient is None:
        conf = config()["memcache"]
        _mcclient = MemcacheClient(
            conf["address"], no_delay=True, default_noreply=False
        )
    return _mcclient


def try_login(account_name, password):
    cur = db().cursor()
    cur.execute(
        "SELECT * FROM users WHERE account_name = %s AND del_flg = 0", (account_name,)
    )
    user = cur.fetchone()

    if user and calculate_passhash(user["account_name"], password) == user["passhash"]:
        return user
    return None


def validate_user(account_name: str, password: str):
    if not re.match(r"[0-9a-zA-Z]{3,}", account_name):
        return False
    if not re.match(r"[0-9a-zA-Z_]{6,}", password):
        return False
    return True


def digest(src: str):
    # opensslのバージョンによっては (stdin)= というのがつくので取る
    out = subprocess.check_output(
        f"printf %s {shlex.quote(src)} | openssl dgst -sha512 | sed 's/^.*= //'",
        shell=True,
        encoding="utf-8",
    )
    return out.strip()


def calculate_salt(account_name: str):
    return digest(account_name)


def calculate_passhash(account_name: str, password: str):
    return digest("%s:%s" % (password, calculate_salt(account_name)))


def get_session_user():
    user = flask.session.get("user")
    if user:
        cur = db().cursor()
        cur.execute("SELECT * FROM `users` WHERE `id` = %s", (user["id"],))
        return cur.fetchone()
    return None


def make_posts(results, all_comments=False):
    if not results:
        return []
    
    posts = []
    cursor = db().cursor()
    
    # 投稿IDとユーザーIDを収集
    post_ids = [post["id"] for post in results]
    user_ids = list(set(post["user_id"] for post in results))
    
    # 一括でコメント数を取得
    cursor.execute(
        "SELECT post_id, COUNT(*) as count FROM comments WHERE post_id IN %s GROUP BY post_id",
        (post_ids,)
    )
    comment_counts = {row["post_id"]: row["count"] for row in cursor.fetchall()}
    
    # 一括でコメントとユーザー情報を取得
    if all_comments:
        cursor.execute("""
            SELECT c.*, u.id as comment_user_id, u.account_name as comment_user_account_name, 
                   u.del_flg as comment_user_del_flg, u.authority as comment_user_authority,
                   u.created_at as comment_user_created_at, u.passhash as comment_user_passhash
            FROM comments c 
            JOIN users u ON c.user_id = u.id 
            WHERE c.post_id IN %s 
            ORDER BY c.post_id, c.created_at DESC
        """, (post_ids,))
    else:
        # サブクエリを使用して各投稿の最新3件のコメントのみ取得
        cursor.execute("""
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
    
    # コメントデータを投稿ごとにグループ化
    comments_by_post = {}
    for row in cursor.fetchall():
        post_id = row["post_id"]
        if post_id not in comments_by_post:
            comments_by_post[post_id] = []
        
        # コメントユーザー情報を構築
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
    
    # 一括で投稿ユーザー情報を取得
    cursor.execute("SELECT * FROM users WHERE id IN %s", (user_ids,))
    users_by_id = {user["id"]: user for user in cursor.fetchall()}
    
    # データを組み立て
    for post in results:
        post["comment_count"] = comment_counts.get(post["id"], 0)
        post_comments = comments_by_post.get(post["id"], [])
        # コメントを古い順に並び替え（reverseと同じ効果）
        post_comments.reverse()
        post["comments"] = post_comments
        post["user"] = users_by_id.get(post["user_id"])

        if post["user"] and not post["user"]["del_flg"]:
            posts.append(post)

        if len(posts) >= POSTS_PER_PAGE:
            break
    
    return posts


# app setup
static_path = pathlib.Path(__file__).resolve().parent.parent / "public"
app = flask.Flask(__name__, static_folder=str(static_path), static_url_path="")
# app.debug = True

# Flask-Session
app.config["SESSION_TYPE"] = "memcached"
app.config["SESSION_MEMCACHED"] = memcache()
Session(app)


@app.template_global()
def image_url(post):
    ext = ""
    mime = post["mime"]
    if mime == "image/jpeg":
        ext = ".jpg"
    elif mime == "image/png":
        ext = ".png"
    elif mime == "image/gif":
        ext = ".gif"

    return "/image/%s%s" % (post["id"], ext)


# http://flask.pocoo.org/snippets/28/
_paragraph_re = re.compile(r"(?:\r\n|\r|\n){2,}")


@app.template_filter()
@pass_eval_context
def nl2br(eval_ctx, value):
    result = "\n\n".join(
        "<p>%s</p>" % p.replace("\n", "<br>\n")
        for p in _paragraph_re.split(escape(value))
    )
    if eval_ctx.autoescape:
        result = Markup(result)
    return result


# endpoints


@app.route("/initialize")
def get_initialize():
    db_initialize()
    return ""


@app.route("/login")
def get_login():
    if get_session_user():
        return flask.redirect("/")
    return flask.render_template("login.html", me=None)


@app.route("/login", methods=["POST"])
def post_login():
    if get_session_user():
        return flask.redirect("/")

    user = try_login(flask.request.form["account_name"], flask.request.form["password"])
    if user:
        flask.session["user"] = {"id": user["id"]}
        flask.session["csrf_token"] = os.urandom(8).hex()
        return flask.redirect("/")

    flask.flash("アカウント名かパスワードが間違っています")
    return flask.redirect("/login")


@app.route("/register")
def get_register():
    if get_session_user():
        return flask.redirect("/")
    return flask.render_template("register.html", me=None)


@app.route("/register", methods=["POST"])
def post_register():
    if get_session_user():
        return flask.redirect("/")

    account_name = flask.request.form["account_name"]
    password = flask.request.form["password"]
    if not validate_user(account_name, password):
        flask.flash(
            "アカウント名は3文字以上、パスワードは6文字以上である必要があります"
        )
        return flask.redirect("/register")

    cursor = db().cursor()
    cursor.execute("SELECT 1 FROM users WHERE `account_name` = %s", (account_name,))
    user = cursor.fetchone()
    if user:
        flask.flash("アカウント名がすでに使われています")
        return flask.redirect("/register")

    query = "INSERT INTO `users` (`account_name`, `passhash`) VALUES (%s, %s)"
    cursor.execute(query, (account_name, calculate_passhash(account_name, password)))

    flask.session["user"] = {"id": cursor.lastrowid}
    flask.session["csrf_token"] = os.urandom(8).hex()
    return flask.redirect("/")


@app.route("/logout")
def get_logout():
    flask.session.clear()
    return flask.redirect("/")


@app.route("/")
def get_index():
    me = get_session_user()

    cursor = db().cursor()
    cursor.execute(
        "SELECT `id`, `user_id`, `body`, `created_at`, `mime` FROM `posts` ORDER BY `created_at` DESC LIMIT %s",
        (POSTS_PER_PAGE * 2,)  # 余裕を持ってフィルタリング後に十分な数を確保
    )
    posts = make_posts(cursor.fetchall())

    return flask.render_template("index.html", posts=posts, me=me)


@app.route("/@<account_name>")
def get_user_list(account_name):
    cursor = db().cursor()

    cursor.execute(
        "SELECT * FROM `users` WHERE `account_name` = %s AND `del_flg` = 0",
        (account_name,),
    )
    user = cursor.fetchone()
    if user is None:
        flask.abort(404)  # raises exception

    cursor.execute(
        "SELECT `id`, `user_id`, `body`, `mime`, `created_at` FROM `posts` WHERE `user_id` = %s ORDER BY `created_at` DESC",
        (user["id"],),
    )
    posts = make_posts(cursor.fetchall())

    cursor.execute(
        "SELECT COUNT(*) AS count FROM `comments` WHERE `user_id` = %s", (user["id"],)
    )
    comment_count = cursor.fetchone()["count"]

    cursor.execute("SELECT `id` FROM `posts` WHERE `user_id` = %s", (user["id"],))
    post_ids = [p["id"] for p in cursor]
    post_count = len(post_ids)

    commented_count = 0
    if post_count > 0:
        cursor.execute(
            "SELECT COUNT(*) AS count FROM `comments` WHERE `post_id` IN %s",
            (post_ids,),
        )
        commented_count = cursor.fetchone()["count"]

    me = get_session_user()

    return flask.render_template(
        "user.html",
        posts=posts,
        user=user,
        post_count=post_count,
        comment_count=comment_count,
        commented_count=commented_count,
        me=me,
    )


def _parse_iso8601(s):
    # http://bugs.python.org/issue15873
    # Ignore timezone
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})[ tT](\d{2}):(\d{2}):(\d{2}).*", s)
    if not m:
        raise ValueError("Invlaid iso8601 format: %r" % (s,))
    return datetime.datetime(*map(int, m.groups()))


@app.route("/posts")
def get_posts():
    cursor = db().cursor()
    max_created_at = flask.request.args["max_created_at"] or None
    if max_created_at:
        max_created_at = _parse_iso8601(max_created_at)
        cursor.execute(
            "SELECT `id`, `user_id`, `body`, `mime`, `created_at` FROM `posts` WHERE `created_at` <= %s ORDER BY `created_at` DESC",
            (max_created_at,),
        )
    else:
        cursor.execute(
            "SELECT `id`, `user_id`, `body`, `mime`, `created_at` FROM `posts` ORDER BY `created_at` DESC LIMIT %s",
            (POSTS_PER_PAGE * 2,)
        )
    results = cursor.fetchall()
    posts = make_posts(results)
    return flask.render_template("posts.html", posts=posts)


@app.route("/posts/<id>")
def get_posts_id(id):
    cursor = db().cursor()

    cursor.execute("SELECT * FROM `posts` WHERE `id` = %s", (id,))
    posts = make_posts(cursor.fetchall(), all_comments=True)
    if not posts:
        flask.abort(404)

    me = get_session_user()
    return flask.render_template("post.html", post=posts[0], me=me)


@app.route("/", methods=["POST"])
def post_index():
    me = get_session_user()
    if not me:
        return flask.redirect("/login")

    if flask.request.form["csrf_token"] != flask.session["csrf_token"]:
        flask.abort(422)

    file = flask.request.files.get("file")
    if not file:
        flask.flash("画像が必要です")
        return flask.redirect("/")

    # 投稿のContent-Typeからファイルのタイプを決定する
    mime = file.mimetype
    if mime not in ("image/jpeg", "image/png", "image/gif"):
        flask.flash("投稿できる画像形式はjpgとpngとgifだけです")
        return flask.redirect("/")

    with tempfile.TemporaryFile() as tempf:
        file.save(tempf)
        tempf.flush()

        if tempf.tell() > UPLOAD_LIMIT:
            flask.flash("ファイルサイズが大きすぎます")
            return flask.redirect("/")

        tempf.seek(0)
        imgdata = tempf.read()

    query = "INSERT INTO `posts` (`user_id`, `mime`, `imgdata`, `body`) VALUES (%s,%s,%s,%s)"
    cursor = db().cursor()
    cursor.execute(query, (me["id"], mime, imgdata, flask.request.form.get("body")))
    pid = cursor.lastrowid
    
    # 画像をファイルシステムにも保存
    save_image_to_file(pid, imgdata, mime)
    
    return flask.redirect("/posts/%d" % pid)


def save_image_to_file(post_id, imgdata, mime):
    """画像をファイルシステムに保存"""
    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif"}
    ext = ext_map.get(mime)
    if not ext:
        return None
    
    # ディレクトリが存在しない場合は作成
    os.makedirs(IMAGE_STORAGE_DIR, exist_ok=True)
    
    filename = f"{post_id}.{ext}"
    filepath = os.path.join(IMAGE_STORAGE_DIR, filename)
    
    try:
        with open(filepath, "wb") as f:
            f.write(imgdata)
        return filename
    except Exception as e:
        flask.current_app.logger.error(f"Failed to save image {filename}: {e}")
        return None

@app.route("/image/<id>.<ext>")
def get_image(id, ext):
    if not id:
        return ""
    id = int(id)
    if id == 0:
        return ""

    # まずファイルシステムから画像を探す
    filepath = os.path.join(IMAGE_STORAGE_DIR, f"{id}.{ext}")
    if os.path.exists(filepath):
        mime_map = {"jpg": "image/jpeg", "png": "image/png", "gif": "image/gif"}
        mime = mime_map.get(ext)
        if mime:
            return flask.send_file(filepath, mimetype=mime)

    # ファイルが存在しない場合、データベースから取得してファイルに保存
    cursor = db().cursor()
    cursor.execute("SELECT `mime`, `imgdata` FROM `posts` WHERE `id` = %s", (id,))
    post = cursor.fetchone()
    
    if not post:
        flask.abort(404)

    mime = post["mime"]
    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif"}
    expected_ext = ext_map.get(mime)
    
    if ext != expected_ext:
        flask.abort(404)
    
    # ファイルに保存
    save_image_to_file(id, post["imgdata"], mime)
    
    return flask.Response(post["imgdata"], mimetype=mime)


@app.route("/comment", methods=["POST"])
def post_comment():
    me = get_session_user()
    if not me:
        return flask.redirect("/login")

    if flask.request.form["csrf_token"] != flask.session["csrf_token"]:
        flask.abort(422)

    post_id = flask.request.form["post_id"]
    if not re.match(r"[0-9]+", post_id):
        return "post_idは整数のみです"
    post_id = int(post_id)

    query = (
        "INSERT INTO `comments` (`post_id`, `user_id`, `comment`) VALUES (%s, %s, %s)"
    )
    cursor = db().cursor()
    cursor.execute(query, (post_id, me["id"], flask.request.form["comment"]))

    return flask.redirect("/posts/%d" % post_id)


@app.route("/admin/banned")
def get_banned():
    me = get_session_user()
    if not me:
        flask.redirect("/login")

    if me["authority"] == 0:
        flask.abort(403)

    cursor = db().cursor()
    cursor.execute(
        "SELECT * FROM `users` WHERE `authority` = 0 AND `del_flg` = 0 ORDER BY `created_at` DESC"
    )
    users = cursor.fetchall()

    flask.render_template("banned.html", users=users, me=me)


@app.route("/admin/banned", methods=["POST"])
def post_banned():
    me = get_session_user()
    if not me:
        flask.redirect("/login")

    if me["authority"] == 0:
        flask.abort(403)

    if flask.request.form["csrf_token"] != flask.session["csrf_token"]:
        flask.abort(422)

    cursor = db().cursor()
    query = "UPDATE `users` SET `del_flg` = %s WHERE `id` = %s"
    for id in flask.request.form.getlist("uid", type=int):
        cursor.execute(query, (1, id))

    return flask.redirect("/admin/banned")
