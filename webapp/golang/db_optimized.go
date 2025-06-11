package main

import (
	"fmt"
	"time"
	"github.com/jmoiron/sqlx"
)

// BatchGetCommentsOptimized gets limited comments for multiple posts using window functions
func batchGetCommentsOptimized(postIDs []int, limit int) (map[int][]Comment, error) {
	if len(postIDs) == 0 {
		return make(map[int][]Comment), nil
	}

	var query string
	if limit > 0 {
		// Use window function to limit comments per post
		query = fmt.Sprintf(`
			WITH ranked_comments AS (
				SELECT 
					c.id, c.post_id, c.user_id, c.comment, c.created_at,
					u.id as user_id_2, u.account_name, u.authority, u.del_flg,
					ROW_NUMBER() OVER (PARTITION BY c.post_id ORDER BY c.created_at DESC) as rn
				FROM comments c
				JOIN users u ON c.user_id = u.id
				WHERE c.post_id IN (?)
			)
			SELECT 
				id, post_id, user_id, comment, created_at,
				user_id_2, account_name, authority, del_flg
			FROM ranked_comments
			WHERE rn <= %d
			ORDER BY post_id, created_at DESC
		`, limit)
	} else {
		query = `
			SELECT 
				c.id, c.post_id, c.user_id, c.comment, c.created_at,
				u.id as user_id_2, u.account_name, u.authority, u.del_flg
			FROM comments c
			JOIN users u ON c.user_id = u.id
			WHERE c.post_id IN (?)
			ORDER BY c.post_id, c.created_at DESC
		`
	}
	
	sqlQuery, args, err := sqlx.In(query, postIDs)
	if err != nil {
		return nil, err
	}
	
	rows, err := db.Query(db.Rebind(sqlQuery), args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	
	commentMap := make(map[int][]Comment)
	
	for rows.Next() {
		var c Comment
		var userID2 int
		err := rows.Scan(
			&c.ID, &c.PostID, &c.UserID, &c.Comment, &c.CreatedAt,
			&userID2, &c.User.AccountName, &c.User.Authority, &c.User.DelFlg,
		)
		if err != nil {
			return nil, err
		}
		c.User.ID = userID2
		
		commentMap[c.PostID] = append(commentMap[c.PostID], c)
	}
	
	return commentMap, nil
}

// GetUsersByIDs gets multiple users by IDs efficiently
func getUsersByIDs(userIDs []int) (map[int]*User, error) {
	if len(userIDs) == 0 {
		return make(map[int]*User), nil
	}

	// Remove duplicates
	uniqueIDs := make(map[int]bool)
	for _, id := range userIDs {
		uniqueIDs[id] = true
	}
	
	ids := make([]int, 0, len(uniqueIDs))
	for id := range uniqueIDs {
		ids = append(ids, id)
	}

	// Check cache first if Redis is available
	userMap := make(map[int]*User)
	needsQuery := []int{}
	
	if redisClient != nil {
		for _, id := range ids {
			if user, err := getUserFromCache(id); err == nil && user != nil {
				userMap[id] = user
			} else {
				needsQuery = append(needsQuery, id)
			}
		}
	} else {
		needsQuery = ids
	}
	
	if len(needsQuery) > 0 {
		query, args, err := sqlx.In("SELECT id, account_name, authority, del_flg FROM users WHERE id IN (?)", needsQuery)
		if err != nil {
			return nil, err
		}
		
		rows, err := db.Query(db.Rebind(query), args...)
		if err != nil {
			return nil, err
		}
		defer rows.Close()
		
		for rows.Next() {
			var u User
			err := rows.Scan(&u.ID, &u.AccountName, &u.Authority, &u.DelFlg)
			if err != nil {
				return nil, err
			}
			userMap[u.ID] = &u
			
			// Cache the user
			if redisClient != nil {
				setUserCache(u, 5*time.Minute)
			}
		}
	}
	
	return userMap, nil
}