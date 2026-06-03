"""GraphRAG query helpers (BE-3).

Provides keyword-driven subgraph extraction for feeding relevant graph
context into the multi-scale QA prompt.
"""

from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph

# ---------------------------------------------------------------------------
# Stop-words removed during keyword extraction so that questions such as
# "这篇论文的核心论点是什么？" yield usable tokens like "核心论点" and "论文".
# ---------------------------------------------------------------------------
_STOP_WORDS: set[str] = {
    "的",
    "了",
    "是",
    "在",
    "和",
    "与",
    "或",
    "这",
    "那",
    "什么",
    "怎么",
    "如何",
    "吗",
    "呢",
    "吧",
    "啊",
    "哪",
    "哪些",
    "一个",
    "一些",
    "这个",
    "那个",
    "这篇",
    "这篇论文",
    "论文",
    "请",
    "请问",
    "一下",
    "为什么",
    "谁",
    "何时",
    "哪里",
}

# ---------------------------------------------------------------------------
# Chinese → English type mapping (for query understanding)
# ---------------------------------------------------------------------------
_CN_TYPE_HINTS: dict[str, str] = {
    # STEM
    "研究问题": "ResearchQuestion",
    "方法": "Method",
    "数据集": "Dataset",
    "指标": "Metric",
    "基线": "Baseline",
    "声称": "Claim",
    "证据": "Evidence",
    "实验": "Experiment",
    # HSS
    "核心论点": "Thesis",
    "论点": "Thesis",
    "分论点": "SubArgument",
    "理论视角": "AnalyticalLens",
    "学脉": "IntellectualContext",
    "研究对象": "ObjectOrData",
    "材料": "ObjectOrData",
    "史料": "ObjectOrData",
    # Edge hints
    "支撑": "SUB_ARGUMENT_OF",
    "挑战": "CHALLENGES",
    "审视": "EXAMINES_THROUGH",
    "支持": "SUPPORTS",
}


class GraphQuery:
    """Multi-hop retriever over a single ``UnifiedPaperGraph``.

    The retriever performs *keyword → node-type → edge traversal* to
    build a relevance-focused subgraph that the QA prompt can consume.
    """

    # ── public API ──────────────────────────────────────────────────────

    def subgraph_for_question(
        self,
        graph: UnifiedPaperGraph,
        question: str,
    ) -> dict:
        """Return a ``{"nodes": [...], "edges": [...]}`` subgraph relevant to *question*.

        Algorithm (no external deps):
        1. Tokenise the Chinese question into usable keywords.
        2. Score nodes by keyword * label / type / data match.
        3. BFS ≤ 2 hops from top-scoring seeds, collecting connecting edges.
        4. Return the induced subgraph as plain dicts.
        """
        keywords = self._extract_keywords(question)

        # ── Phase 1: score & seed nodes ─────────────────────────────
        node_scores: dict[str, float] = {}
        for node in graph.nodes:
            score = self._score_node(node, keywords)
            if score > 0:
                node_scores[node.id] = score

        if not node_scores:
            # Fallback: return all top-level nodes (Thesis / ResearchQuestion)
            return self._fallback_subgraph(graph)

        seeds: set[str] = set(node_scores)

        # ── Phase 2: build adjacency ────────────────────────────────
        adj: dict[str, list[tuple[str, GraphEdge]]] = {n.id: [] for n in graph.nodes}
        edge_index: dict[str, GraphEdge] = {}
        for e in graph.edges:
            if e.source in adj:
                adj[e.source].append((e.target, e))
            if e.target in adj:
                adj[e.target].append((e.source, e))
            edge_index[e.id] = e

        # ── Phase 3: 2-hop BFS ──────────────────────────────────────
        visited: set[str] = set(seeds)
        collected_edges: set[str] = set()
        frontier: list[str] = list(seeds)

        for _hop in range(2):
            if not frontier:
                break
            next_frontier: list[str] = []
            for nid in frontier:
                for neighbour, edge in adj.get(nid, []):
                    collected_edges.add(edge.id)
                    if neighbour not in visited:
                        visited.add(neighbour)
                        next_frontier.append(neighbour)
            frontier = next_frontier

        # ── Phase 4: materialise ────────────────────────────────────
        return {
            "nodes": [n.model_dump() for n in graph.nodes if n.id in visited],
            "edges": [e.model_dump() for e in graph.edges if e.id in collected_edges],
        }

    # ── helpers ────────────────────────────────────────────────────────

    def _extract_keywords(self, question: str) -> list[str]:
        """Extract meaningful Chinese phrases / entity names from *question*."""
        cleaned = (
            question.replace("？", " ")
            .replace("？", " ")
            .replace("，", " ")
            .replace("。", " ")
            .replace("；", " ")
            .replace("：", " ")
            .replace("、", " ")
            .replace("「", "")
            .replace("」", "")
            .replace("”", "")
            .replace("“", "")
        )
        tokens = [t for t in cleaned.split() if t not in _STOP_WORDS and len(t) >= 2]

        raw = cleaned.replace(" ", "")
        ngrams: list[str] = []
        for n in (4, 3, 2):
            for i in range(len(raw) - n + 1):
                chunk = raw[i : i + n]
                if chunk not in _STOP_WORDS:
                    ngrams.append(chunk)

        seen: set[str] = set()
        keywords: list[str] = []
        for kw in tokens + ngrams:
            if kw not in seen:
                seen.add(kw)
                keywords.append(kw)

        # Prepend English type hints so they survive the cap
        hints: list[str] = []
        for kw in keywords:
            hint = _CN_TYPE_HINTS.get(kw)
            if hint and hint not in seen:
                seen.add(hint)
                hints.append(hint)

        keywords = hints + keywords
        return keywords[:40]

    def _score_node(self, node: GraphNode, keywords: list[str]) -> float:
        """Score a single node against the keyword list."""
        text = f"{node.label} {node.type} {' '.join(str(v) for v in node.data.values())}"
        text_lower = text.lower()
        score = 0.0
        for kw in keywords:
            if kw.lower() in text_lower:
                score += 1.0
        return score

    def _fallback_subgraph(self, graph: UnifiedPaperGraph) -> dict:
        """Return minimal subgraph containing top-level nodes only."""
        if graph.paradigm.value == "HSS":
            top_types = {"Thesis", "SubArgument"}
        else:
            top_types = {"ResearchQuestion", "Claim", "Method"}

        top_ids = {n.id for n in graph.nodes if n.type in top_types}
        top_edges = [e for e in graph.edges if e.source in top_ids and e.target in top_ids]
        return {
            "nodes": [n.model_dump() for n in graph.nodes if n.id in top_ids],
            "edges": [e.model_dump() for e in top_edges],
        }
