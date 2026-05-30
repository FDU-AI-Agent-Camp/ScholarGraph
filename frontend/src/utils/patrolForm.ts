/** Patrol form helpers (paper_ids parsing and validation). */

export const PATROL_PAPER_COUNT = 2

export function parsePatrolPaperIds(text: string): string[] {
  return text
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
}

export function validatePatrolPaperIds(paperIds: string[]): string | null {
  if (paperIds.length !== PATROL_PAPER_COUNT) {
    return `巡检需要恰好 ${PATROL_PAPER_COUNT} 篇 ready 论文 ID（当前 ${paperIds.length} 篇）`
  }
  return null
}

export function formatPatrolError(code: string | null, message: string): string {
  if (code === 'GRAPH_NOT_READY') {
    return `${message}（请先在后端执行 uv run python scripts/run_patrol.py --seed-demo-graphs）`
  }
  if (code === 'PATROL_INSUFFICIENT_DATA') {
    return `${message}（图谱缺少 Lens / Thesis 节点，可切换巡检模式或重新 seed）`
  }
  return message
}
