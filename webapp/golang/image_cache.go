package main

import (
	"bytes"
	"crypto/md5"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"strconv"
	"sync"
	"time"
)

// ImageCache handles caching of images both in memory and on filesystem
type ImageCache struct {
	memoryCache  map[string]*CachedImage
	cacheDir     string
	mutex        sync.RWMutex
	maxMemoryMB  int
	currentMemMB int
}

// CachedImage represents a cached image
type CachedImage struct {
	Data        []byte
	Mime        string
	LastAccess  time.Time
	Size        int
}

var imageCache *ImageCache

// InitImageCache initializes the image cache system
func InitImageCache() {
	cacheDir := os.Getenv("ISUCONP_IMAGE_CACHE_DIR")
	if cacheDir == "" {
		cacheDir = "/tmp/isuconp_cache"
	}
	
	maxMemoryMB := 100 // Default 100MB
	if envMemory := os.Getenv("ISUCONP_CACHE_MEMORY_MB"); envMemory != "" {
		if parsed, err := strconv.Atoi(envMemory); err == nil {
			maxMemoryMB = parsed
		}
	}

	// Create cache directory if it doesn't exist
	if err := os.MkdirAll(cacheDir, 0755); err != nil {
		log.Printf("Failed to create cache directory: %v", err)
		return
	}

	imageCache = &ImageCache{
		memoryCache:  make(map[string]*CachedImage),
		cacheDir:     cacheDir,
		maxMemoryMB:  maxMemoryMB,
		currentMemMB: 0,
	}

	log.Printf("Image cache initialized with directory: %s, max memory: %dMB", cacheDir, maxMemoryMB)
}

// getCacheKey generates a cache key for a post ID
func getCacheKey(postID int) string {
	return fmt.Sprintf("post_%d", postID)
}

// getFileCachePath returns the file system cache path for a post
func (ic *ImageCache) getFileCachePath(postID int, mime string) string {
	ext := getExtensionFromMime(mime)
	return filepath.Join(ic.cacheDir, fmt.Sprintf("%d%s", postID, ext))
}

// getExtensionFromMime returns file extension based on MIME type
func getExtensionFromMime(mime string) string {
	switch mime {
	case "image/jpeg":
		return ".jpg"
	case "image/png":
		return ".png"
	case "image/gif":
		return ".gif"
	default:
		return ".bin"
	}
}

// Get retrieves an image from cache (memory first, then filesystem, then database)
func (ic *ImageCache) Get(postID int) (*CachedImage, bool) {
	if ic == nil {
		return nil, false
	}

	key := getCacheKey(postID)
	
	ic.mutex.RLock()
	// Check memory cache first
	if cached, exists := ic.memoryCache[key]; exists {
		cached.LastAccess = time.Now()
		ic.mutex.RUnlock()
		return cached, true
	}
	ic.mutex.RUnlock()

	// Check filesystem cache
	post := Post{}
	err := db.Get(&post, "SELECT `mime` FROM `posts` WHERE `id` = ?", postID)
	if err != nil {
		return nil, false
	}

	filePath := ic.getFileCachePath(postID, post.Mime)
	if data, err := os.ReadFile(filePath); err == nil {
		// File exists in cache, load into memory cache
		cached := &CachedImage{
			Data:       data,
			Mime:       post.Mime,
			LastAccess: time.Now(),
			Size:       len(data),
		}
		
		ic.addToMemoryCache(key, cached)
		return cached, true
	}

	return nil, false
}

// Set stores an image in both memory and filesystem cache
func (ic *ImageCache) Set(postID int, data []byte, mime string) {
	if ic == nil {
		return
	}

	key := getCacheKey(postID)
	cached := &CachedImage{
		Data:       data,
		Mime:       mime,
		LastAccess: time.Now(),
		Size:       len(data),
	}

	// Store in filesystem cache
	filePath := ic.getFileCachePath(postID, mime)
	if err := os.WriteFile(filePath, data, 0644); err != nil {
		log.Printf("Failed to write to filesystem cache: %v", err)
	}

	// Store in memory cache
	ic.addToMemoryCache(key, cached)
}

// addToMemoryCache adds an image to memory cache with size management
func (ic *ImageCache) addToMemoryCache(key string, cached *CachedImage) {
	ic.mutex.Lock()
	defer ic.mutex.Unlock()

	sizeMB := cached.Size / (1024 * 1024)
	
	// Check if we need to evict items
	for ic.currentMemMB+sizeMB > ic.maxMemoryMB && len(ic.memoryCache) > 0 {
		ic.evictLRU()
	}

	ic.memoryCache[key] = cached
	ic.currentMemMB += sizeMB
}

// evictLRU removes the least recently used item from memory cache
func (ic *ImageCache) evictLRU() {
	var oldestKey string
	var oldestTime time.Time = time.Now()

	for key, cached := range ic.memoryCache {
		if cached.LastAccess.Before(oldestTime) {
			oldestTime = cached.LastAccess
			oldestKey = key
		}
	}

	if oldestKey != "" {
		if cached, exists := ic.memoryCache[oldestKey]; exists {
			ic.currentMemMB -= cached.Size / (1024 * 1024)
			delete(ic.memoryCache, oldestKey)
		}
	}
}

// GetCacheStats returns cache statistics
func (ic *ImageCache) GetCacheStats() map[string]interface{} {
	if ic == nil {
		return map[string]interface{}{}
	}

	ic.mutex.RLock()
	defer ic.mutex.RUnlock()

	return map[string]interface{}{
		"memory_items":    len(ic.memoryCache),
		"memory_usage_mb": ic.currentMemMB,
		"memory_limit_mb": ic.maxMemoryMB,
		"cache_directory": ic.cacheDir,
	}
}

// ClearCache clears both memory and filesystem cache
func (ic *ImageCache) ClearCache() {
	if ic == nil {
		return
	}

	ic.mutex.Lock()
	defer ic.mutex.Unlock()

	// Clear memory cache
	ic.memoryCache = make(map[string]*CachedImage)
	ic.currentMemMB = 0

	// Clear filesystem cache
	if err := os.RemoveAll(ic.cacheDir); err != nil {
		log.Printf("Failed to clear filesystem cache: %v", err)
	} else {
		os.MkdirAll(ic.cacheDir, 0755)
	}

	log.Println("Image cache cleared")
}