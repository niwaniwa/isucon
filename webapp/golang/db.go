package main

import (
	"github.com/jmoiron/sqlx"
)

// BatchGetUsers gets multiple users by IDs in a single query
func batchGetUsers(userIDs []int) (map[int]*User, error) {
	if len(userIDs) == 0 {
		return make(map[int]*User), nil
	}

	query, args, err := sqlx.In("SELECT * FROM users WHERE id IN (?)", userIDs)
	if err != nil {
		return nil, err
	}
	
	var users []User
	err = db.Select(&users, db.Rebind(query), args...)
	if err != nil {
		return nil, err
	}
	
	userMap := make(map[int]*User)
	for i := range users {
		userMap[users[i].ID] = &users[i]
	}
	
	return userMap, nil
}

// BatchGetComments gets all comments for multiple posts in a single query
func batchGetComments(postIDs []int, limit int) (map[int][]Comment, error) {
	if len(postIDs) == 0 {
		return make(map[int][]Comment), nil
	}

	// For now, get all comments and limit in application
	// This is still better than N+1 queries
	query := `
		SELECT c.*, u.id as 'user.id', u.account_name as 'user.account_name', 
		       u.authority as 'user.authority', u.del_flg as 'user.del_flg',
		       u.passhash as 'user.passhash', u.created_at as 'user.created_at'
		FROM comments c
		JOIN users u ON c.user_id = u.id
		WHERE c.post_id IN (?)
		ORDER BY c.post_id, c.created_at DESC
	`
	
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
	commentCounts := make(map[int]int)
	
	for rows.Next() {
		var c Comment
		var u User
		err := rows.Scan(
			&c.ID, &c.PostID, &c.UserID, &c.Comment, &c.CreatedAt,
			&u.ID, &u.AccountName, &u.Authority, &u.DelFlg,
			&u.Passhash, &u.CreatedAt,
		)
		if err != nil {
			return nil, err
		}
		c.User = u
		
		// Apply limit per post if needed
		if limit > 0 && commentCounts[c.PostID] >= limit {
			continue
		}
		
		commentMap[c.PostID] = append(commentMap[c.PostID], c)
		commentCounts[c.PostID]++
	}
	
	return commentMap, nil
}

// GetCommentCounts gets comment counts for multiple posts in a single query
func getCommentCounts(postIDs []int) (map[int]int, error) {
	if len(postIDs) == 0 {
		return make(map[int]int), nil
	}

	query, args, err := sqlx.In(`
		SELECT post_id, COUNT(*) as count 
		FROM comments 
		WHERE post_id IN (?) 
		GROUP BY post_id
	`, postIDs)
	if err != nil {
		return nil, err
	}
	
	type result struct {
		PostID int `db:"post_id"`
		Count  int `db:"count"`
	}
	
	var results []result
	err = db.Select(&results, db.Rebind(query), args...)
	if err != nil {
		return nil, err
	}
	
	countMap := make(map[int]int)
	for _, r := range results {
		countMap[r.PostID] = r.Count
	}
	
	// Set 0 for posts without comments
	for _, postID := range postIDs {
		if _, ok := countMap[postID]; !ok {
			countMap[postID] = 0
		}
	}
	
	return countMap, nil
}