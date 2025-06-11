-- パフォーマンス向上のためのインデックス追加

-- 投稿の created_at でのソート用（DESC順序）
ALTER TABLE posts ADD INDEX idx_posts_created_at (created_at DESC);

-- ユーザーIDによる投稿検索用
ALTER TABLE posts ADD INDEX idx_posts_user_id (user_id);

-- 投稿IDによるコメント検索用
ALTER TABLE comments ADD INDEX idx_comments_post_id (post_id);

-- ユーザーIDによるコメント検索用
ALTER TABLE comments ADD INDEX idx_comments_user_id (user_id);

-- 削除フラグでの絞り込み用
ALTER TABLE users ADD INDEX idx_users_del_flg (del_flg);

-- 複合インデックス（より効率的なクエリのため）
ALTER TABLE posts ADD INDEX idx_posts_user_created (user_id, created_at DESC);
ALTER TABLE comments ADD INDEX idx_comments_post_created (post_id, created_at DESC); 