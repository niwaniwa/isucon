import os
import sys
import MySQLdb
import MySQLdb.cursors

# --- 設定 ---
DB_CONFIG = {
    "host": os.environ.get("ISUCONP_DB_HOST", "localhost"),
    "port": int(os.environ.get("ISUCONP_DB_PORT", "3306")),
    "user": os.environ.get("ISUCONP_DB_USER", "isuconp"),
    "passwd": os.environ.get("ISUCONP_DB_PASSWORD", "isuconp"),
    "db": os.environ.get("ISUCONP_DB_NAME", "isuconp"),
    "charset": "utf8mb4",
    "cursorclass": MySQLdb.cursors.DictCursor,
    "autocommit": True,
}

IMAGE_STORAGE_DIR = "/var/www/images"

def main():
    """DBから画像データを読み込み、ファイルに保存してDBを更新する"""
    
    print("Connecting to the database...")
    conn = MySQLdb.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # 画像保存ディレクトリを作成
    os.makedirs(IMAGE_STORAGE_DIR, exist_ok=True)
    print(f"Image storage directory: '{IMAGE_STORAGE_DIR}'")

    # まだファイルパスが設定されていない投稿を取得
    cursor.execute("SELECT id, mime, imgdata FROM posts WHERE imgdata IS NOT NULL AND filepath IS NULL")
    posts = cursor.fetchall()
    
    if not posts:
        print("No images to migrate. Exiting.")
        return

    print(f"Found {len(posts)} images to migrate.")

    for post in posts:
        post_id = post["id"]
        mime_type = post["mime"]
        image_data = post["imgdata"]

        if not mime_type or not image_data:
            print(f"Skipping post {post_id} due to missing mime or data.")
            continue
        
        # MIMEタイプから拡張子を決定
        ext = ""
        if mime_type == "image/jpeg":
            ext = ".jpg"
        elif mime_type == "image/png":
            ext = ".png"
        elif mime_type == "image/gif":
            ext = ".gif"
        else:
            print(f"Skipping post {post_id} due to unsupported mime type: {mime_type}")
            continue

        # ファイルパスを生成
        filename = f"{post_id}{ext}"
        filepath = os.path.join(IMAGE_STORAGE_DIR, filename)
        
        try:
            # 画像データをファイルとして保存
            with open(filepath, "wb") as f:
                f.write(image_data)
            
            # DBのfilepathを更新
            cursor.execute("UPDATE posts SET filepath = %s WHERE id = %s", (filepath, post_id))
            print(f"  - Migrated post {post_id} -> {filepath}")

        except Exception as e:
            print(f"  - FAILED to migrate post {post_id}: {e}")

    cursor.close()
    conn.close()
    print("Python script finished.")

if __name__ == "__main__":
    main()