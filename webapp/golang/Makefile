.PHONY: all build clean run migrate

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
