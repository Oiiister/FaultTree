.PHONY: help install build dev-backend dev-frontend test

help:
	@echo "常用命令："
	@echo "  make install      安装后端(uv)与前端(bun)依赖"
	@echo "  make build        构建前端资源到 backend/lightrag/api/webui"
	@echo "  make dev-backend  启动后端 (0.0.0.0:9621)"
	@echo "  make dev-frontend 启动前端 dev server (5173)"
	@echo "  make test         运行后端测试"

install:
	cd backend && uv sync --extra api --extra offline
	cd frontend && bun install --frozen-lockfile

build:
	cd frontend && bun run build

dev-backend:
	cd backend && python -m lightrag.api.lightrag_server

dev-frontend:
	cd frontend && bun run dev

test:
	cd backend && uv run pytest
