package main

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"
)

// TestImageCachePerformance benchmarks the image cache system
func BenchmarkImageCache(b *testing.B) {
	// Initialize test data
	InitImageCache()
	
	testData := []byte("test image data")
	testMime := "image/jpeg"
	testPostID := 1
	
	b.ResetTimer()
	
	b.Run("Cache_Set", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			imageCache.Set(testPostID+i, testData, testMime)
		}
	})
	
	// Populate cache for get test
	imageCache.Set(testPostID, testData, testMime)
	
	b.Run("Cache_Get_Hit", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			_, found := imageCache.Get(testPostID)
			if !found {
				b.Fatal("Cache miss when hit expected")
			}
		}
	})
	
	b.Run("Cache_Get_Miss", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			_, found := imageCache.Get(testPostID + 10000 + i)
			if found {
				b.Fatal("Cache hit when miss expected")
			}
		}
	})
}

// BenchmarkImageEndpoint tests the image serving endpoint performance
func BenchmarkImageEndpoint(b *testing.B) {
	// Mock the database connection for testing
	if db == nil {
		b.Skip("Database not available for benchmark")
		return
	}
	
	InitImageCache()
	
	// Create test server
	r := setupTestRouter()
	server := httptest.NewServer(r)
	defer server.Close()
	
	// Test with cache miss (first request)
	b.Run("Image_Request_Cache_Miss", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			url := fmt.Sprintf("%s/image/%d.jpg", server.URL, i%1000+1)
			resp, err := http.Get(url)
			if err != nil {
				b.Fatal(err)
			}
			io.Copy(io.Discard, resp.Body)
			resp.Body.Close()
		}
	})
	
	// Test with cache hit (subsequent requests)
	testImageID := 1
	warmupURL := fmt.Sprintf("%s/image/%d.jpg", server.URL, testImageID)
	resp, _ := http.Get(warmupURL)
	if resp != nil {
		resp.Body.Close()
	}
	
	b.Run("Image_Request_Cache_Hit", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			url := fmt.Sprintf("%s/image/%d.jpg", server.URL, testImageID)
			resp, err := http.Get(url)
			if err != nil {
				b.Fatal(err)
			}
			io.Copy(io.Discard, resp.Body)
			resp.Body.Close()
		}
	})
}

// BenchmarkGzipMiddleware tests gzip compression performance
func BenchmarkGzipMiddleware(b *testing.B) {
	testData := bytes.Repeat([]byte("test data for compression"), 1000)
	
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write(testData)
	})
	
	b.Run("Without_Gzip", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			req := httptest.NewRequest("GET", "/test", nil)
			w := httptest.NewRecorder()
			handler.ServeHTTP(w, req)
		}
	})
	
	gzipHandler := GzipMiddleware(handler)
	
	b.Run("With_Gzip", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			req := httptest.NewRequest("GET", "/test", nil)
			req.Header.Set("Accept-Encoding", "gzip")
			w := httptest.NewRecorder()
			gzipHandler.ServeHTTP(w, req)
		}
	})
}

// setupTestRouter creates a test router with minimal configuration
func setupTestRouter() http.Handler {
	r := chi.NewRouter()
	
	// Apply middleware
	r.Use(SecurityHeadersMiddleware)
	r.Use(CacheControlMiddleware)
	r.Use(GzipMiddleware)
	r.Use(ETagMiddleware)
	
	r.Get("/image/{id}.{ext}", getImage)
	r.Get("/admin/cache/stats", getCacheStats)
	
	return r
}

// TestCacheEviction tests the LRU cache eviction mechanism
func TestCacheEviction(t *testing.T) {
	// Set a small cache size for testing
	os.Setenv("ISUCONP_CACHE_MEMORY_MB", "1")
	InitImageCache()
	
	// Create test data larger than 1MB total
	largeData := make([]byte, 500*1024) // 500KB per image
	
	// Fill cache beyond capacity
	for i := 0; i < 5; i++ {
		imageCache.Set(i, largeData, "image/jpeg")
	}
	
	stats := imageCache.GetCacheStats()
	memoryItems := stats["memory_items"].(int)
	
	if memoryItems > 3 {
		t.Errorf("Expected cache to evict items, but found %d items", memoryItems)
	}
	
	// Clean up
	os.Unsetenv("ISUCONP_CACHE_MEMORY_MB")
}

// TestHTTPCacheHeaders tests cache header functionality
func TestHTTPCacheHeaders(t *testing.T) {
	r := setupTestRouter()
	
	tests := []struct {
		path           string
		expectedCache  string
	}{
		{"/image/1.jpg", "public, max-age=31536000"},
		{"/static/style.css", "public, max-age=86400"},
		{"/", "no-cache, must-revalidate"},
	}
	
	for _, tt := range tests {
		req := httptest.NewRequest("GET", tt.path, nil)
		w := httptest.NewRecorder()
		
		r.ServeHTTP(w, req)
		
		cacheControl := w.Header().Get("Cache-Control")
		if cacheControl != tt.expectedCache {
			t.Errorf("Path %s: expected Cache-Control %s, got %s", 
				tt.path, tt.expectedCache, cacheControl)
		}
	}
}

// TestETagFunctionality tests ETag conditional request handling
func TestETagFunctionality(t *testing.T) {
	if db == nil {
		t.Skip("Database not available for test")
		return
	}
	
	InitImageCache()
	r := setupTestRouter()
	
	// First request to get ETag
	req1 := httptest.NewRequest("GET", "/image/1.jpg", nil)
	w1 := httptest.NewRecorder()
	r.ServeHTTP(w1, req1)
	
	etag := w1.Header().Get("ETag")
	if etag == "" {
		t.Fatal("Expected ETag header in response")
	}
	
	// Second request with If-None-Match
	req2 := httptest.NewRequest("GET", "/image/1.jpg", nil)
	req2.Header.Set("If-None-Match", etag)
	w2 := httptest.NewRecorder()
	r.ServeHTTP(w2, req2)
	
	if w2.Code != http.StatusNotModified {
		t.Errorf("Expected 304 Not Modified, got %d", w2.Code)
	}
}

// BenchmarkMemoryVsFileSystemCache compares memory and filesystem cache performance
func BenchmarkMemoryVsFileSystemCache(b *testing.B) {
	InitImageCache()
	
	testData := make([]byte, 100*1024) // 100KB test image
	testMime := "image/jpeg"
	postID := 1
	
	// Populate filesystem cache
	imageCache.Set(postID, testData, testMime)
	
	// Clear memory cache to force filesystem read
	imageCache.mutex.Lock()
	imageCache.memoryCache = make(map[string]*CachedImage)
	imageCache.currentMemMB = 0
	imageCache.mutex.Unlock()
	
	b.Run("Filesystem_Cache_Read", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			// Clear memory cache each time to force filesystem read
			imageCache.mutex.Lock()
			delete(imageCache.memoryCache, getCacheKey(postID))
			imageCache.mutex.Unlock()
			
			_, found := imageCache.Get(postID)
			if !found {
				b.Fatal("Expected to find cached image")
			}
		}
	})
	
	// Ensure image is in memory cache
	imageCache.Set(postID, testData, testMime)
	
	b.Run("Memory_Cache_Read", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			_, found := imageCache.Get(postID)
			if !found {
				b.Fatal("Expected to find cached image")
			}
		}
	})
}