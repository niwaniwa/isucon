-- ISUCONアプリケーション最適化用SQL
-- パフォーマンス向上のためのインデックス追加

-- Users テーブルの最適化
ALTER TABLE users ADD INDEX idx_account_name_del_flg (account_name, del_flg);
ALTER TABLE users ADD INDEX idx_authority_del_flg (authority, del_flg);
ALTER TABLE users ADD INDEX idx_created_at (created_at);

-- Posts テーブルの最適化
ALTER TABLE posts ADD INDEX idx_user_id_created_at (user_id, created_at);
ALTER TABLE posts ADD INDEX idx_created_at (created_at);

-- Comments テーブルの最適化
ALTER TABLE comments ADD INDEX idx_post_id_created_at (post_id, created_at);
ALTER TABLE comments ADD INDEX idx_user_id (user_id);
ALTER TABLE comments ADD INDEX idx_post_id_user_id (post_id, user_id);

-- 既存のインデックスを確認（必要に応じて）
-- SHOW INDEX FROM users;
-- SHOW INDEX FROM posts;
-- SHOW INDEX FROM comments;

-- パフォーマンス分析用クエリ（開発用）
-- EXPLAIN SELECT * FROM users WHERE account_name = ? AND del_flg = 0;
-- EXPLAIN SELECT COUNT(*) FROM comments WHERE post_id = ?;
-- EXPLAIN SELECT * FROM posts ORDER BY created_at DESC LIMIT 20;