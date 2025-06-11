package main

import (
	"fmt"
	"strings"
)

// BatchGetUsers retrieves multiple users in a single query
func BatchGetUsers(userIDs []int) (map[int]User, error) {
	if len(userIDs) == 0 {
		return make(map[int]User), nil
	}
	
	// Remove duplicates
	uniqueIDs := make(map[int]bool)
	for _, id := range userIDs {
		uniqueIDs[id] = true
	}
	
	// Convert back to slice
	ids := make([]int, 0, len(uniqueIDs))
	for id := range uniqueIDs {
		ids = append(ids, id)
	}
	
	// Build query
	placeholders := strings.Repeat("?,", len(ids))
	placeholders = placeholders[:len(placeholders)-1] // Remove trailing comma
	
	query := fmt.Sprintf("SELECT * FROM `users` WHERE `id` IN (%s)", placeholders)
	
	// Convert int slice to interface slice
	args := make([]interface{}, len(ids))
	for i, id := range ids {
		args[i] = id
	}
	
	var users []User
	err := db.Select(&users, query, args...)
	if err != nil {
		return nil, err
	}
	
	// Convert to map
	userMap := make(map[int]User)
	for _, user := range users {
		userMap[user.ID] = user
	}
	
	return userMap, nil
}

// BatchGetComments retrieves comments for multiple posts
func BatchGetComments(postIDs []int, limit int) (map[int][]Comment, error) {
	if len(postIDs) == 0 {
		return make(map[int][]Comment), nil
	}
	
	// Remove duplicates
	uniqueIDs := make(map[int]bool)
	for _, id := range postIDs {
		uniqueIDs[id] = true
	}
	
	// Convert back to slice
	ids := make([]int, 0, len(uniqueIDs))
	for id := range uniqueIDs {
		ids = append(ids, id)
	}
	
	// Build query
	placeholders := strings.Repeat("?,", len(ids))
	placeholders = placeholders[:len(placeholders)-1] // Remove trailing comma
	
	query := fmt.Sprintf(`
		SELECT * FROM (
			SELECT *, ROW_NUMBER() OVER (PARTITION BY post_id ORDER BY created_at DESC) as rn
			FROM comments 
			WHERE post_id IN (%s)
		) ranked 
		WHERE rn <= ?
		ORDER BY post_id, created_at ASC
	`, placeholders)
	
	// Convert int slice to interface slice and add limit
	args := make([]interface{}, len(ids)+1)
	for i, id := range ids {
		args[i] = id
	}
	args[len(ids)] = limit
	
	var comments []Comment
	err := db.Select(&comments, query, args...)
	if err != nil {
		return nil, err
	}
	
	// Group by post_id
	commentMap := make(map[int][]Comment)
	for _, comment := range comments {
		commentMap[comment.PostID] = append(commentMap[comment.PostID], comment)
	}
	
	return commentMap, nil
}

// BatchGetCommentCounts retrieves comment counts for multiple posts
func BatchGetCommentCounts(postIDs []int) (map[int]int, error) {
	if len(postIDs) == 0 {
		return make(map[int]int), nil
	}
	
	// Remove duplicates
	uniqueIDs := make(map[int]bool)
	for _, id := range postIDs {
		uniqueIDs[id] = true
	}
	
	// Convert back to slice
	ids := make([]int, 0, len(uniqueIDs))
	for id := range uniqueIDs {
		ids = append(ids, id)
	}
	
	// Build query
	placeholders := strings.Repeat("?,", len(ids))
	placeholders = placeholders[:len(placeholders)-1] // Remove trailing comma
	
	query := fmt.Sprintf("SELECT post_id, COUNT(*) as count FROM `comments` WHERE `post_id` IN (%s) GROUP BY post_id", placeholders)
	
	// Convert int slice to interface slice
	args := make([]interface{}, len(ids))
	for i, id := range ids {
		args[i] = id
	}
	
	type CommentCount struct {
		PostID int `db:"post_id"`
		Count  int `db:"count"`
	}
	
	var counts []CommentCount
	err := db.Select(&counts, query, args...)
	if err != nil {
		return nil, err
	}
	
	// Convert to map
	countMap := make(map[int]int)
	for _, count := range counts {
		countMap[count.PostID] = count.Count
	}
	
	// Fill in zeros for posts with no comments
	for _, id := range ids {
		if _, exists := countMap[id]; !exists {
			countMap[id] = 0
		}
	}
	
	return countMap, nil
}