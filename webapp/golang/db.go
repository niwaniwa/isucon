package main

import (
	"time"
	"github.com/jmoiron/sqlx"
)

// BatchGetUsers gets multiple users by IDs in a single query (with deduplication and caching)
func batchGetUsers(userIDs []int) (map[int]*User, error) {
	return getUsersByIDs(userIDs)
}

// BatchGetComments gets all comments for multiple posts in a single query
func batchGetComments(postIDs []int, limit int) (map[int][]Comment, error) {
	// Use optimized version with window functions
	return batchGetCommentsOptimized(postIDs, limit)
}

// GetCommentCounts gets comment counts for multiple posts in a single query
func getCommentCounts(postIDs []int) (map[int]int, error) {
	if len(postIDs) == 0 {
		return make(map[int]int), nil
	}

	countMap := make(map[int]int)
	needsQuery := []int{}

	// Check Redis cache first
	if redisClient != nil {
		for _, postID := range postIDs {
			if count, found := getCommentCountFromCache(postID); found {
				countMap[postID] = count
			} else {
				needsQuery = append(needsQuery, postID)
			}
		}
	} else {
		needsQuery = postIDs
	}

	// Query database for missing counts
	if len(needsQuery) > 0 {
		query, args, err := sqlx.In(`
			SELECT post_id, COUNT(*) as count 
			FROM comments 
			WHERE post_id IN (?) 
			GROUP BY post_id
		`, needsQuery)
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
		
		// Process results and cache them
		for _, r := range results {
			countMap[r.PostID] = r.Count
			if redisClient != nil {
				setCommentCountCache(r.PostID, r.Count, 5*time.Minute)
			}
		}
		
		// Set 0 for posts without comments and cache them too
		for _, postID := range needsQuery {
			if _, ok := countMap[postID]; !ok {
				countMap[postID] = 0
				if redisClient != nil {
					setCommentCountCache(postID, 0, 5*time.Minute)
				}
			}
		}
	}
	
	return countMap, nil
}