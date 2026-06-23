.PHONY: check check-lint check-no-fix test format type

# 完整后端门禁：ruff -> pyright -> pytest（前一步失败则停止）
check:
	uv run python scripts/check_backend.py

# 仅静态检查（ruff + pyright），不跑测试
check-lint:
	uv run python scripts/check_backend.py --lint-only

# CI 模式：ruff check 不自动修复 + pyright + pytest
check-no-fix:
	uv run python scripts/check_backend.py --no-fix

# 单独步骤
type:
	uv run pyright backend

format:
	uv run ruff format backend tests scripts
	uv run ruff check --fix backend tests scripts

test:
	uv run python -m pytest -q --tb=short -m "not red and not live_mineru and not live_grobid and not live_benchmark"
