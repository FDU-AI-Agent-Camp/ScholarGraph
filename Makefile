.PHONY: check check-lint check-no-fix ci ci-patrol-release ci-demo-profile-check p13-release-gate process-release-gate pipeline-repo-lod format type test

# PR 门禁：排除所有 live / 外部依赖 marker，仅跑内存 Stub 回归
PR_GATE_MARKERS := not red and not live_patrol_logic and not live_qa_logic and not demo_profile_check and not live_mineru and not live_grobid and not live_benchmark and not live_e10 and not live_judge and not live_head_merge

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
	uv run python scripts/check_rag_io_timeouts.py
	uv run python scripts/check_pipeline_repo_lod.py
	uv run python scripts/check_services_no_run_async.py
	uv run python scripts/check_async_hotpath_await.py
	uv run python scripts/check_p13_release_gate.py
	uv run python scripts/check_process_release_gate.py
	uv run python -m pytest -q --tb=short --cov=backend --cov-report=xml --cov-report=term-missing --cov-fail-under=30 -m "$(PR_GATE_MARKERS)"
	uv run pip-audit --desc --format=json --local --path=.venv > pip-audit-report.json || true

# PaperService 封装边界：禁止 backend 其他模块触碰 ._pipeline_repo
pipeline-repo-lod:
	uv run python scripts/check_pipeline_repo_lod.py

# P13 孤儿线程 / Watchdog 债务回归矩阵（也可单独本地跑）
p13-release-gate:
	uv run python scripts/check_p13_release_gate.py

# processing / pending 墙钟 Watchdog + 冷启动 grace（平行于 P13）
process-release-gate:
	uv run python scripts/check_process_release_gate.py

# Nightly / Release 门禁：processing 假死自愈硬卡 + patrol golden + live_patrol + demo + live benchmark
ci-patrol-release:
	uv run python scripts/check_process_release_gate.py
	uv run python scripts/validate_patrol_golden.py --strict --json
	uv run python -m pytest -q --tb=short tests/patrol/ -m "not live_patrol_logic"
	uv run python -m pytest -q --tb=short -m patrol_fault_injection
	uv run python -m pytest -q --tb=short -m live_patrol_logic
	uv run python -m pytest -q --tb=short -m demo_profile_check
	uv run python scripts/benchmark_patrol.py --mode all --live

# Demo / Staging 准入（本地或 staging 手动执行）
ci-demo-profile-check:
	uv run python -m pytest -q --tb=short -m demo_profile_check

# 单独步骤
type:
	uv run pyright backend

format:
	uv run ruff format backend tests scripts
	uv run ruff check --fix backend tests scripts

test:
	uv run python -m pytest -q --tb=short -m "$(PR_GATE_MARKERS)"
