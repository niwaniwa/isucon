.PHONY: all build clean run migrate

export ISUCONP_DB_HOST=${ISUCONP_DB_HOST:-localhost}
export ISUCONP_DB_PORT=${ISUCONP_DB_PORT:-3306}
export ISUCONP_DB_USER=${ISUCONP_DB_USER:-root}
export ISUCONP_DB_PASSWORD=${ISUCONP_DB_PASSWORD:-}
export ISUCONP_DB_NAME=${ISUCONP_DB_NAME:-isuconp}
export REDIS_HOST=${REDIS_HOST:-localhost}
export REDIS_PORT=${REDIS_PORT:-6379}

all: build

build: go.mod go.sum
	go build -o app .

clean:
	rm -f app

run: build
	./app

migrate:
	go run cmd/migrate/migrate.go

# For development with hot reload
dev:
	which air > /dev/null || go install github.com/cosmtrek/air@latest
	air
