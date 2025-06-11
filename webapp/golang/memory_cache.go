package main

import (
	"sync"
	"time"
)

// MemoryCache is a simple in-memory cache with expiration
type MemoryCache struct {
	data  map[string]*CacheItem
	mutex sync.RWMutex
}

// CacheItem represents a cached item with expiration
type CacheItem struct {
	Value      interface{}
	Expiration time.Time
}

var memoryCache *MemoryCache

// InitMemoryCache initializes the memory cache
func InitMemoryCache() {
	memoryCache = &MemoryCache{
		data: make(map[string]*CacheItem),
	}
	
	// Start cleanup routine
	go memoryCache.cleanup()
}

// Set stores a value in the cache with expiration
func (mc *MemoryCache) Set(key string, value interface{}, expiration time.Duration) {
	mc.mutex.Lock()
	defer mc.mutex.Unlock()
	
	mc.data[key] = &CacheItem{
		Value:      value,
		Expiration: time.Now().Add(expiration),
	}
}

// Get retrieves a value from the cache
func (mc *MemoryCache) Get(key string) (interface{}, bool) {
	mc.mutex.RLock()
	defer mc.mutex.RUnlock()
	
	item, exists := mc.data[key]
	if !exists {
		return nil, false
	}
	
	if time.Now().After(item.Expiration) {
		delete(mc.data, key)
		return nil, false
	}
	
	return item.Value, true
}

// Delete removes a value from the cache
func (mc *MemoryCache) Delete(key string) {
	mc.mutex.Lock()
	defer mc.mutex.Unlock()
	
	delete(mc.data, key)
}

// Clear removes all values from the cache
func (mc *MemoryCache) Clear() {
	mc.mutex.Lock()
	defer mc.mutex.Unlock()
	
	mc.data = make(map[string]*CacheItem)
}

// cleanup removes expired items periodically
func (mc *MemoryCache) cleanup() {
	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()
	
	for {
		select {
		case <-ticker.C:
			mc.mutex.Lock()
			now := time.Now()
			for key, item := range mc.data {
				if now.After(item.Expiration) {
					delete(mc.data, key)
				}
			}
			mc.mutex.Unlock()
		}
	}
}

// Size returns the number of items in the cache
func (mc *MemoryCache) Size() int {
	mc.mutex.RLock()
	defer mc.mutex.RUnlock()
	
	return len(mc.data)
}