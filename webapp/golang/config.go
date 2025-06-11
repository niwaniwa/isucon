package main

import (
	"os"
	"strconv"
)

// Config holds application configuration
type Config struct {
	DBHost               string
	DBPort               string
	DBUser               string
	DBPassword           string
	DBName               string
	MemcachedAddress     string
	RedisHost            string
	RedisPort            string
	ImageCacheDir        string
	ImageDir             string
	CacheMemoryMB        int
	MaxOpenConns         int
	MaxIdleConns         int
}

// LoadConfig loads configuration from environment variables
func LoadConfig() *Config {
	config := &Config{
		DBHost:           getEnv("ISUCONP_DB_HOST", "localhost"),
		DBPort:           getEnv("ISUCONP_DB_PORT", "3306"),
		DBUser:           getEnv("ISUCONP_DB_USER", "root"),
		DBPassword:       getEnv("ISUCONP_DB_PASSWORD", ""),
		DBName:           getEnv("ISUCONP_DB_NAME", "isuconp"),
		MemcachedAddress: getEnv("ISUCONP_MEMCACHED_ADDRESS", "localhost:11211"),
		RedisHost:        getEnv("REDIS_HOST", "localhost"),
		RedisPort:        getEnv("REDIS_PORT", "6379"),
		ImageCacheDir:    getEnv("ISUCONP_IMAGE_CACHE_DIR", "/tmp/isuconp_cache"),
		ImageDir:         getEnv("ISUCONP_IMAGE_DIR", "/var/www/images"),
		CacheMemoryMB:    getEnvInt("ISUCONP_CACHE_MEMORY_MB", 100),
		MaxOpenConns:     getEnvInt("ISUCONP_MAX_OPEN_CONNS", 25),
		MaxIdleConns:     getEnvInt("ISUCONP_MAX_IDLE_CONNS", 25),
	}
	
	return config
}

// getEnv gets environment variable with default value
func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

// getEnvInt gets environment variable as integer with default value
func getEnvInt(key string, defaultValue int) int {
	if value := os.Getenv(key); value != "" {
		if intValue, err := strconv.Atoi(value); err == nil {
			return intValue
		}
	}
	return defaultValue
}