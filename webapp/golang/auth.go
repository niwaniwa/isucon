package main

import (
	"crypto/sha512"
	"encoding/hex"
)

// calculateSaltNative calculates salt using native Go implementation
func calculateSaltNative(accountName string) string {
	h := sha512.New()
	h.Write([]byte(accountName))
	return hex.EncodeToString(h.Sum(nil))
}

// calculatePasshashNative calculates password hash using native Go implementation
func calculatePasshashNative(accountName, password string) string {
	salt := calculateSaltNative(accountName)
	h := sha512.New()
	h.Write([]byte(password + ":" + salt))
	return hex.EncodeToString(h.Sum(nil))
}