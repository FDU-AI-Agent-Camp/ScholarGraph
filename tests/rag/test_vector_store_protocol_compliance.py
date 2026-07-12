"""契约合规性测试：校验所有 VectorStore 实现是否顺从 ``VectorStoreProtocol``。"""

from __future__ import annotations

import inspect
from typing import Any, get_type_hints

import pytest
import backend.rag.hybrid_retriever as hybrid_retriever_module
import backend.rag.protocols as protocols_module
import backend.rag.static_mock_vector_store as static_mock_module
import backend.rag.vector_store as vector_store_module
import tests.helpers.vector_store_doubles as vector_store_doubles_module
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.models import RetrievedChunk, RetrievedEntity, RetrievedRelation
from backend.rag.protocols import VectorStoreProtocol
from backend.rag.static_mock_vector_store import StaticMockVectorStore
from backend.rag.vector_store import VectorStore
from tests.helpers.vector_store_doubles import SlowGetChunkStore

_QUERY_METHODS = ("query_chunks", "query_entities", "query_relations")
_PREVIEW_METHODS = ("exists", "get_chunk_text")
_QUERY_KWONLY_PARAMS = ("paper_id", "top_k", "query_embedding")
_RETURN_TYPES_BY_METHOD = {
    "query_chunks": list[RetrievedChunk],
    "query_entities": list[RetrievedEntity],
    "query_relations": list[RetrievedRelation],
}
VECTOR_STORE_COMPLIANCE_MATRIX: list[tuple[type[Any], object]] = [
    (VectorStore, vector_store_module),
    (StaticMockVectorStore, static_mock_module),
    (SlowGetChunkStore, vector_store_doubles_module),
]
_IMPL_MODULE_BY_CLS = dict(VECTOR_STORE_COMPLIANCE_MATRIX)


def _hints_module_for_store(store_cls: type[Any]) -> object:
    if issubclass(store_cls, StaticMockVectorStore):
        return static_mock_module
    return _IMPL_MODULE_BY_CLS[store_cls]


def _type_hints(obj: object, *, module: object) -> dict[str, Any]:
    return get_type_hints(obj, globalns=vars(module), localns=None)


def _public_params(signature: inspect.Signature) -> list[inspect.Parameter]:
    return [param for name, param in signature.parameters.items() if name != "self"]


def _contract_param_tuple(param: inspect.Parameter) -> tuple[str, inspect._ParameterKind, object, object]:
    return (param.name, param.kind, param.default, param.annotation)


def test_known_vector_store_impl_registry_covers_production_and_test_doubles() -> None:
    registered = {cls.__name__ for cls, _ in VECTOR_STORE_COMPLIANCE_MATRIX}
    assert registered == {"VectorStore", "StaticMockVectorStore", "SlowGetChunkStore"}


@pytest.mark.parametrize("store_cls", [cls for cls, _ in VECTOR_STORE_COMPLIANCE_MATRIX])
def test_compile_time_guard_present_for_production_stores(store_cls: type[Any]) -> None:
    if store_cls is VectorStore:
        assert "_inspect_compliance" in vector_store_module.__dict__
    elif store_cls is StaticMockVectorStore:
        assert "_inspect_mock_compliance" in static_mock_module.__dict__
    else:
        assert issubclass(store_cls, StaticMockVectorStore)


@pytest.mark.parametrize("store_cls", [cls for cls, _ in VECTOR_STORE_COMPLIANCE_MATRIX])
@pytest.mark.parametrize("method_name", _QUERY_METHODS)
def test_vector_store_methods_compliance(store_cls: type[Any], method_name: str) -> None:
    """验证所有向量库实现是否严格契合 Protocol 约定的签名参数。"""
    assert hasattr(store_cls, method_name), f"{store_cls.__name__} 缺少必要方法 {method_name}"

    protocol_sig = inspect.signature(getattr(VectorStoreProtocol, method_name))
    impl_sig = inspect.signature(getattr(store_cls, method_name))

    assert "query_embedding" in impl_sig.parameters, f"{store_cls.__name__}.{method_name} 未适配 'query_embedding' 参数"
    assert impl_sig.parameters["query_embedding"].default is None
    assert protocol_sig.parameters["query_embedding"].default is None

    protocol_view = [_contract_param_tuple(param) for param in _public_params(protocol_sig)]
    impl_view = [_contract_param_tuple(param) for param in _public_params(impl_sig)]
    assert impl_view == protocol_view, (
        f"{store_cls.__name__}.{method_name} 参数顺序/类型与 VectorStoreProtocol 不一致\n"
        f"protocol={protocol_view}\nimpl={impl_view}"
    )

    for param_name in _QUERY_KWONLY_PARAMS:
        assert param_name in impl_sig.parameters, f"{store_cls.__name__}.{method_name} 缺少参数 {param_name!r}"
        assert impl_sig.parameters[param_name].kind is inspect.Parameter.KEYWORD_ONLY


@pytest.mark.parametrize("store_cls", [cls for cls, _ in VECTOR_STORE_COMPLIANCE_MATRIX])
@pytest.mark.parametrize("method_name", _QUERY_METHODS)
def test_query_embedding_annotation_matches_protocol(store_cls: type[Any], method_name: str) -> None:
    """断言 query_embedding 的类型注解与 Protocol 一致，防止隐式 Any 泄露。"""
    protocol_method = getattr(VectorStoreProtocol, method_name)
    impl_method = getattr(store_cls, method_name)
    protocol_hints = _type_hints(protocol_method, module=protocols_module)
    impl_hints = _type_hints(impl_method, module=_hints_module_for_store(store_cls))

    for param_name in ("query_text", "paper_id", "top_k", "query_embedding"):
        assert protocol_hints[param_name] == impl_hints[param_name]
    assert impl_hints["query_embedding"] == list[float] | None


@pytest.mark.parametrize("store_cls", [cls for cls, _ in VECTOR_STORE_COMPLIANCE_MATRIX])
@pytest.mark.parametrize("method_name", _QUERY_METHODS)
def test_query_return_types_match_protocol(store_cls: type[Any], method_name: str) -> None:
    """断言 query_* 返回值注解为具体 Pydantic 领域模型列表，禁止 list[Any]/dict。"""
    protocol_method = getattr(VectorStoreProtocol, method_name)
    impl_method = getattr(store_cls, method_name)
    protocol_hints = _type_hints(protocol_method, module=protocols_module)
    impl_hints = _type_hints(impl_method, module=_hints_module_for_store(store_cls))

    assert protocol_hints["return"] == _RETURN_TYPES_BY_METHOD[method_name]
    assert impl_hints["return"] == protocol_hints["return"]
    assert impl_hints["return"] is not Any


@pytest.mark.parametrize("store_cls", [cls for cls, _ in VECTOR_STORE_COMPLIANCE_MATRIX])
def test_exists_return_type_is_bool(store_cls: type[Any]) -> None:
    protocol_hints = _type_hints(VectorStoreProtocol.exists, module=protocols_module)
    impl_hints = _type_hints(store_cls.exists, module=_hints_module_for_store(store_cls))
    assert protocol_hints["return"] is bool
    assert impl_hints["return"] is bool


@pytest.mark.parametrize("store_cls", [cls for cls, _ in VECTOR_STORE_COMPLIANCE_MATRIX])
@pytest.mark.parametrize("method_name", _PREVIEW_METHODS)
def test_vector_store_preview_methods_declared(store_cls: type[Any], method_name: str) -> None:
    assert hasattr(store_cls, method_name), f"{store_cls.__name__} 缺少必要方法 {method_name}"
    assert "paper_id" in inspect.signature(getattr(store_cls, method_name)).parameters


@pytest.mark.parametrize("method_name", _QUERY_METHODS)
def test_protocol_top_k_default_is_optional_none(method_name: str) -> None:
    """松紧契约：top_k 缺省为 None，由实现侧解析默认 top-k，避免 Mock/真实库分流。"""
    protocol_sig = inspect.signature(getattr(VectorStoreProtocol, method_name))
    top_k_param = protocol_sig.parameters["top_k"]
    assert top_k_param.default is None
    assert top_k_param.annotation in (int | None, "int | None")


def test_hybrid_retriever_vector_store_annotation_uses_protocol() -> None:
    init_hints = _type_hints(HybridRetriever.__init__, module=hybrid_retriever_module)
    assert init_hints["vector_store"] == VectorStoreProtocol | None

    init_signature = inspect.signature(HybridRetriever.__init__)
    vector_store_param = init_signature.parameters["vector_store"]
    assert vector_store_param.annotation is not inspect.Parameter.empty


def test_hybrid_retriever_retrieve_vectors_query_embedding_type_closed() -> None:
    """审计 _retrieve_vectors → query_* 调用栈中 query_embedding 的强类型约束。"""
    retrieve_vectors_hints = _type_hints(HybridRetriever._retrieve_vectors, module=hybrid_retriever_module)
    retrieve_vectors_sig = inspect.signature(HybridRetriever._retrieve_vectors)
    retrieve_sig = inspect.signature(HybridRetriever.retrieve)

    assert retrieve_vectors_hints["query_embedding"] == list[float] | None
    assert retrieve_vectors_sig.parameters["query_embedding"].annotation == retrieve_sig.parameters["query_embedding"].annotation
    assert str(retrieve_vectors_sig.parameters["query_embedding"].annotation) == "list[float] | None"
    assert retrieve_vectors_sig.parameters["query_embedding"].default is inspect.Parameter.empty
    assert retrieve_sig.parameters["query_embedding"].default is None

    vector_store_param = inspect.signature(HybridRetriever.__init__).parameters["vector_store"]
    assert vector_store_param.annotation is not inspect.Parameter.empty


@pytest.mark.asyncio
@pytest.mark.parametrize("store_cls", [StaticMockVectorStore, SlowGetChunkStore])
@pytest.mark.parametrize(
    ("top_k", "method_name"),
    [
        (None, "query_chunks"),
        (2, "query_chunks"),
        (None, "query_entities"),
        (1, "query_relations"),
    ],
)
async def test_optional_top_k_runtime_boundaries(
    store_cls: type[Any],
    top_k: int | None,
    method_name: str,
) -> None:
    store = store_cls.load_default() if hasattr(store_cls, "load_default") else store_cls(chunks_by_paper={})
    method = getattr(store, method_name)
    kwargs: dict[str, Any] = {"paper_id": "stem-001", "query_embedding": None}
    if top_k is not None:
        kwargs["top_k"] = top_k
    result = await method("ImageNet accuracy", **kwargs)
    assert isinstance(result, list)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "query_embedding"),
    [
        ("query_chunks", None),
        ("query_chunks", [0.1, 0.2, 0.3]),
        ("query_entities", None),
        ("query_entities", [0.4, 0.5]),
        ("query_relations", None),
        ("query_relations", [0.6]),
    ],
)
async def test_static_mock_vector_store_accepts_query_embedding_kwarg(
    method_name: str,
    query_embedding: list[float] | None,
) -> None:
    store = StaticMockVectorStore(chunks_by_paper={})
    method = getattr(store, method_name)
    result = await method(
        "ResNet accuracy on ImageNet",
        paper_id="stem-001",
        top_k=3,
        query_embedding=query_embedding,
    )
    assert isinstance(result, list)
