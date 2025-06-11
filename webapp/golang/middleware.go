package main

import (
	"compress/gzip"
	"fmt"
	"io"
	"log"
	"net/http"
	"strconv"
	"strings"
	"time"
)

// GzipResponseWriter wraps http.ResponseWriter to provide gzip compression
type GzipResponseWriter struct {
	http.ResponseWriter
	gw *gzip.Writer
}

func (grw *GzipResponseWriter) Write(b []byte) (int, error) {
	return grw.gw.Write(b)
}

func (grw *GzipResponseWriter) Close() error {
	return grw.gw.Close()
}

// GzipMiddleware provides gzip compression for responses
func GzipMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Check if client accepts gzip
		if !strings.Contains(r.Header.Get("Accept-Encoding"), "gzip") {
			next.ServeHTTP(w, r)
			return
		}

		// Set gzip headers
		w.Header().Set("Content-Encoding", "gzip")
		w.Header().Set("Vary", "Accept-Encoding")

		// Create gzip writer
		gw := gzip.NewWriter(w)
		defer gw.Close()

		grw := &GzipResponseWriter{
			ResponseWriter: w,
			gw:             gw,
		}

		next.ServeHTTP(grw, r)
	})
}

// CacheControlMiddleware sets appropriate cache headers
func CacheControlMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Set cache headers based on path
		if strings.HasPrefix(r.URL.Path, "/image/") {
			// Images can be cached for a long time
			w.Header().Set("Cache-Control", "public, max-age=31536000") // 1 year
			w.Header().Set("Expires", time.Now().Add(365*24*time.Hour).Format(http.TimeFormat))
		} else if strings.HasPrefix(r.URL.Path, "/static/") || 
				  strings.HasSuffix(r.URL.Path, ".css") || 
				  strings.HasSuffix(r.URL.Path, ".js") {
			// Static assets can be cached for a moderate time
			w.Header().Set("Cache-Control", "public, max-age=86400") // 1 day
		} else {
			// Dynamic content should not be cached
			w.Header().Set("Cache-Control", "no-cache, must-revalidate")
		}

		next.ServeHTTP(w, r)
	})
}

// SecurityHeadersMiddleware adds security headers
func SecurityHeadersMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("X-Frame-Options", "DENY")
		w.Header().Set("X-XSS-Protection", "1; mode=block")
		w.Header().Set("Referrer-Policy", "strict-origin-when-cross-origin")
		
		next.ServeHTTP(w, r)
	})
}

// LoggingMiddleware logs HTTP requests
func LoggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		
		next.ServeHTTP(w, r)
		
		duration := time.Since(start)
		if duration > 100*time.Millisecond {
			log.Printf("Slow request: %s %s took %v", r.Method, r.URL.Path, duration)
		}
	})
}

// ETags middleware for conditional requests
func ETagMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// For image requests, add ETag support
		if strings.HasPrefix(r.URL.Path, "/image/") {
			// Extract post ID from path
			if postID := extractPostIDFromPath(r.URL.Path); postID > 0 {
				etag := generateETag(postID)
				w.Header().Set("ETag", etag)
				
				// Check If-None-Match header
				if match := r.Header.Get("If-None-Match"); match == etag {
					w.WriteHeader(http.StatusNotModified)
					return
				}
			}
		}
		
		next.ServeHTTP(w, r)
	})
}

// extractPostIDFromPath extracts post ID from image URL path
func extractPostIDFromPath(path string) int {
	// Simple extraction - you might want to use regex for more robust parsing
	parts := strings.Split(path, "/")
	if len(parts) >= 3 && parts[1] == "image" {
		// Remove extension
		filename := parts[2]
		dotIndex := strings.LastIndex(filename, ".")
		if dotIndex > 0 {
			filename = filename[:dotIndex]
		}
		if id, err := strconv.Atoi(filename); err == nil {
			return id
		}
	}
	return 0
}

// generateETag generates an ETag for a post
func generateETag(postID int) string {
	return fmt.Sprintf(`"%d"`, postID)
}