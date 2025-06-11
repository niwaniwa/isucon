package main

import (
	"fmt"
	"os"
	"path/filepath"
)

const imageDir = "../public/image"

// initImageDir creates the image directory if it doesn't exist
func initImageDir() error {
	return os.MkdirAll(imageDir, 0755)
}

// saveImageToFile saves image data to filesystem
func saveImageToFile(postID int, mime string, data []byte) error {
	ext := getExtension(mime)
	if ext == "" {
		return fmt.Errorf("invalid mime type: %s", mime)
	}
	
	filename := fmt.Sprintf("%d%s", postID, ext)
	path := filepath.Join(imageDir, filename)
	
	return os.WriteFile(path, data, 0644)
}

// loadImageFromFile loads image data from filesystem
func loadImageFromFile(postID int, ext string) ([]byte, error) {
	filename := fmt.Sprintf("%d.%s", postID, ext)
	path := filepath.Join(imageDir, filename)
	
	return os.ReadFile(path)
}

// getExtension returns file extension for mime type
func getExtension(mime string) string {
	switch mime {
	case "image/jpeg":
		return ".jpg"
	case "image/png":
		return ".png"
	case "image/gif":
		return ".gif"
	default:
		return ""
	}
}

// copyImageData copies image data from database to filesystem (for migration)
func copyImageData(postID int, mime string, data []byte) error {
	if len(data) == 0 {
		return nil
	}
	return saveImageToFile(postID, mime, data)
}