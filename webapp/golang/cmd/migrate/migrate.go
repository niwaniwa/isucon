package main

import (
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"time"

	"github.com/jmoiron/sqlx"
	_ "github.com/go-sql-driver/mysql"
)

const imageDir = "../../public/image"

// Run this as a separate command to migrate images from DB to filesystem
// cd webapp/golang && go run cmd/migrate/migrate.go
func main() {
	var dsn string
	flag.StringVar(&dsn, "dsn", "", "MySQL DSN")
	flag.Parse()

	if dsn == "" {
		// Build DSN from environment variables
		host := os.Getenv("ISUCONP_DB_HOST")
		if host == "" {
			host = "localhost"
		}
		port := os.Getenv("ISUCONP_DB_PORT")
		if port == "" {
			port = "3306"
		}
		user := os.Getenv("ISUCONP_DB_USER")
		if user == "" {
			user = "root"
		}
		password := os.Getenv("ISUCONP_DB_PASSWORD")
		dbname := os.Getenv("ISUCONP_DB_NAME")
		if dbname == "" {
			dbname = "isuconp"
		}
		dsn = fmt.Sprintf("%s:%s@tcp(%s:%s)/%s?charset=utf8mb4&parseTime=true&loc=Local",
			user, password, host, port, dbname)
	}

	db, err := sqlx.Open("mysql", dsn)
	if err != nil {
		log.Fatalf("Failed to connect to DB: %s", err.Error())
	}
	defer db.Close()

	// Initialize image directory
	if err := os.MkdirAll(imageDir, 0755); err != nil {
		log.Fatalf("Failed to initialize image directory: %s", err.Error())
	}

	// Get all posts with images
	type PostImage struct {
		ID      int    `db:"id"`
		Mime    string `db:"mime"`
		Imgdata []byte `db:"imgdata"`
	}

	var posts []PostImage
	err = db.Select(&posts, "SELECT id, mime, imgdata FROM posts WHERE imgdata IS NOT NULL AND LENGTH(imgdata) > 0")
	if err != nil {
		log.Fatalf("Failed to get posts: %s", err.Error())
	}

	log.Printf("Found %d posts with images to migrate", len(posts))

	// Migrate each image
	success := 0
	failed := 0
	
	for i, post := range posts {
		if i%100 == 0 {
			log.Printf("Progress: %d/%d", i, len(posts))
		}
		
		ext := ""
		switch post.Mime {
		case "image/jpeg":
			ext = ".jpg"
		case "image/png":
			ext = ".png"
		case "image/gif":
			ext = ".gif"
		default:
			log.Printf("Unknown mime type for post %d: %s", post.ID, post.Mime)
			failed++
			continue
		}
		
		filename := fmt.Sprintf("%d%s", post.ID, ext)
		path := filepath.Join(imageDir, filename)
		
		err := os.WriteFile(path, post.Imgdata, 0644)
		if err != nil {
			log.Printf("Failed to save image for post %d: %s", post.ID, err.Error())
			failed++
			continue
		}
		
		// Optional: Clear imgdata from database to save space
		// _, err = db.Exec("UPDATE posts SET imgdata = '' WHERE id = ?", post.ID)
		// if err != nil {
		// 	log.Printf("Failed to clear imgdata for post %d: %s", post.ID, err.Error())
		// }
		
		success++
		time.Sleep(10 * time.Millisecond) // Small delay to avoid overwhelming the filesystem
	}

	log.Printf("Migration completed: %d successful, %d failed", success, failed)
}