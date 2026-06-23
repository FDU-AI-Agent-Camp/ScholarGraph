.PHONY: check check-lint check-no-fix ci format type test

# 完整后端门禁：ruff --fix -> ruff format -> pyright -> pytest
# 适合本地开发快速验证
check:
	uv run python scripts/check_backend.py

# 仅静态检查（ruff + pyright），不跑测试
check-lint:
	uv run python scripts/check_backend.py --lint-only

# CI 模式：ruff check 不自动修复 + ruff format check + pyright + pytest
# 主要用于线上 Ubuntu 一键执行；Windows 本地建议直接用 scripts/check_backend.py
check-no-fix:
	uv run python scripts/check_backend.py --no-fix

# 完整 CI 流程（供 GitHub Actions 使用）：
# ruff check -> ruff format check -> pyright -> pytest with coverage -> pip-audit
ci:
	uv run ruff check backend tests scripts
	uv run ruff format --check backend tests scripts
	uv run pyright backend
	uv run python -m pytest -q --tb=short --cov=backend --cov-report=xml --cov-report=term-missing --cov-fail-under=30 -m "not red and not live_mineru and not live_grobid"
	uv run pip-audit --desc --format=json --local --path=.venv > pip-audit-report.json || true

# 单独步骤
type:
	uv run pyright backend

format:
	uv run ruff format backend tests scripts
	uv run ruff check --fix backend tests scripts

test:
	uv run python -m pytest -q --tb=short -m "not red and not live_mineru and not live_grobid and not live_benchmark"
