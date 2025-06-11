package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"time"

	"github.com/redis/go-redis/v9"
)

var (
	redisClient *redis.Client
	ctx         = context.Background()
)

func initRedis() error {
	host := os.Getenv("REDIS_HOST")
	if host == "" {
		host = "localhost"
	}
	port := os.Getenv("REDIS_PORT")
	if port == "" {
		port = "6379"
	}

	redisClient = redis.NewClient(&redis.Options{
		Addr:         fmt.Sprintf("%s:%s", host, port),
		Password:     "", // no password set
		DB:           0,  // use default DB
		PoolSize:     10,
		MinIdleConns: 5,
	})

	// Test connection
	_, err := redisClient.Ping(ctx).Result()
	return err
}

// Redis cache functions

// GetUserFromCache gets user from Redis cache
func getUserFromCache(userID int) (*User, error) {
	key := fmt.Sprintf("user:%d", userID)
	val, err := redisClient.Get(ctx, key).Result()
	if err == redis.Nil {
		return nil, nil // Cache miss
	} else if err != nil {
		return nil, err
	}

	var user User
	err = json.Unmarshal([]byte(val), &user)
	if err != nil {
		return nil, err
	}

	return &user, nil
}

// SetUserCache sets user in Redis cache
func setUserCache(user User, expiration time.Duration) error {
	key := fmt.Sprintf("user:%d", user.ID)
	data, err := json.Marshal(user)
	if err != nil {
		return err
	}

	return redisClient.Set(ctx, key, data, expiration).Err()
}

// DeleteUserCache removes user from cache
func deleteUserCache(userID int) error {
	key := fmt.Sprintf("user:%d", userID)
	return redisClient.Del(ctx, key).Err()
}

// GetPostsFromCache gets posts from Redis cache
func getPostsFromCache(key string) ([]Post, error) {
	val, err := redisClient.Get(ctx, key).Result()
	if err == redis.Nil {
		return nil, nil // Cache miss
	} else if err != nil {
		return nil, err
	}

	var posts []Post
	err = json.Unmarshal([]byte(val), &posts)
	if err != nil {
		return nil, err
	}

	return posts, nil
}

// SetPostsCache sets posts in Redis cache
func setPostsCache(key string, posts []Post, expiration time.Duration) error {
	data, err := json.Marshal(posts)
	if err != nil {
		return err
	}

	return redisClient.Set(ctx, key, data, expiration).Err()
}

// InvalidatePostsCaches invalidates all posts-related caches
func invalidatePostsCaches() error {
	// Just invalidate the main index cache
	// User-specific caches will expire naturally
	return redisClient.Del(ctx, "posts:index:latest").Err()
}

// InvalidateUserPostsCache invalidates posts cache for a specific user
func invalidateUserPostsCache(userID int) error {
	key := fmt.Sprintf("posts:user:%d", userID)
	return redisClient.Del(ctx, key).Err()
}

// GetCommentCountFromCache gets comment count from Redis cache
func getCommentCountFromCache(postID int) (int, bool) {
	key := fmt.Sprintf("comment_count:%d", postID)
	val, err := redisClient.Get(ctx, key).Result()
	if err != nil {
		return 0, false
	}

	var count int
	_, err = fmt.Sscanf(val, "%d", &count)
	if err != nil {
		return 0, false
	}

	return count, true
}

// SetCommentCountCache sets comment count in Redis cache
func setCommentCountCache(postID int, count int, expiration time.Duration) error {
	key := fmt.Sprintf("comment_count:%d", postID)
	return redisClient.Set(ctx, key, fmt.Sprintf("%d", count), expiration).Err()
}

// InvalidateCommentCountCache invalidates comment count cache for a post
func invalidateCommentCountCache(postID int) error {
	key := fmt.Sprintf("comment_count:%d", postID)
	return redisClient.Del(ctx, key).Err()
}