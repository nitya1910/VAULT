.PHONY: up down build test demo clean

up:
	docker compose up -d

build:
	docker compose up --build -d

down:
	docker compose down

test:
	docker compose -f docker-compose.test.yml up --build --abort-on-container-exit

demo:
	python scripts/demo.py

clean:
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -r {} \+
