"""Cloud adapters. Every request requires an authorized outbound scope."""

import hashlib
import hmac
import json
import os
import re
import threading
import time
from collections import deque
from collections.abc import Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from tcm_platform.audit import append_event
from tcm_platform.db import SessionLocal
from tcm_platform.ids import new_id
from tcm_platform.model_credentials import read_model_key
from tcm_platform.models import ModelInvocation
from tcm_platform.outbound_policy import POLICY_VERSION, current_permit, require_outbound

MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_REQUEST_BYTES = 1024 * 1024
MAX_REQUESTS_PER_MINUTE = 60
MAX_IN_FLIGHT = 4
TRANSIENT_HTTP_STATUS = {429, 500, 502, 503, 504}
WORKSPACE = re.compile(r"^[a-zA-Z0-9-]{1,100}$")
_gate_lock = threading.Lock()
_in_flight = threading.BoundedSemaphore(MAX_IN_FLIGHT)
_requests: dict[str, deque[float]] = {}
_failures: dict[str, int] = {}
_open_until: dict[str, float] = {}


def _admit_request(host: str) -> None:
    now = time.monotonic()
    with _gate_lock:
        if _open_until.get(host, 0) > now:
            raise RuntimeError("cloud model circuit is open")
        recent = _requests.setdefault(host, deque())
        while recent and recent[0] <= now - 60:
            recent.popleft()
        if len(recent) >= MAX_REQUESTS_PER_MINUTE:
            raise RuntimeError("cloud model rate limit reached")
        recent.append(now)


def _transport_result(host: str, success: bool) -> None:
    with _gate_lock:
        if success:
            _failures[host] = 0
        else:
            _failures[host] = _failures.get(host, 0) + 1
            if _failures[host] >= 3:
                _open_until[host] = time.monotonic() + 30


def _checked_endpoint(url: str) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.port not in (None, 443)
        or parsed.hostname is None
        or not (
            parsed.hostname == "api.siliconflow.cn"
            or parsed.hostname == "api.deepseek.com"
            or parsed.hostname.endswith(".maas.aliyuncs.com")
        )
    ):
        raise ValueError("model endpoint must be an approved HTTPS provider host")
    return url


def _checked_route(provider: str, operation: str, endpoint: str) -> str:
    endpoint = _checked_endpoint(endpoint)
    parsed = urlparse(endpoint)
    if provider == "siliconflow":
        expected = {"embed": "/v1/embeddings", "rerank": "/v1/rerank"}[operation]
        valid = parsed.hostname == "api.siliconflow.cn" and parsed.path == expected
    elif provider == "aliyun":
        expected = {"embed": "/compatible-mode/v1/embeddings",
                    "rerank": "/api/v1/services/rerank/text-rerank/text-rerank"}[operation]
        valid = parsed.hostname.endswith(".maas.aliyuncs.com") and parsed.path == expected
    else:
        valid = False
    if not valid:
        raise ValueError("model endpoint does not match provider and operation")
    return endpoint


def _record_start(endpoint: str, request_hash: str):
    permit = current_permit()
    invocation_id = new_id()
    with SessionLocal.begin() as session:
        session.add(ModelInvocation(
            id=invocation_id, task_id=permit.task_id, agent_run_id=None,
            purpose=permit.operation, model_version=permit.model_version,
            endpoint=endpoint, request_hash=request_hash, output_hash=None,
            token_usage=None, latency_ms=0, status="STARTED", error_class=None,
            policy_hash=permit.policy_hash, policy_version=POLICY_VERSION,
            transport_retry_count=0,
        ))
        append_event(session, event_type="model.outbound_started", actor_id="model-gateway",
                     aggregate_id=invocation_id,
                     payload={"operation": permit.operation, "policy_hash": permit.policy_hash,
                              "source_count": len(permit.source_ids)})
    return invocation_id


def _record_finish(invocation_id, *, output_hash: str | None,
                   latency_ms: int, retry_count: int, error_class: str | None) -> None:
    with SessionLocal.begin() as session:
        invocation = session.get(ModelInvocation, invocation_id, with_for_update=True)
        if invocation is None or invocation.status != "STARTED":
            raise RuntimeError("outbound invocation record disappeared")
        invocation.output_hash = output_hash
        invocation.latency_ms = latency_ms
        invocation.transport_retry_count = retry_count
        invocation.error_class = error_class
        invocation.status = "FAILED" if error_class else "COMPLETED"
        append_event(session, event_type="model.outbound_finished", actor_id="model-gateway",
                     aggregate_id=invocation_id,
                     payload={"status": invocation.status, "retry_count": retry_count})


def _post_json(url: str, api_key: str, payload: dict) -> dict:
    if not api_key:
        raise ValueError("cloud model API key is not configured")
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_REQUEST_BYTES:
        raise ValueError("cloud model request exceeds size limit")
    endpoint = _checked_endpoint(url)
    host = urlparse(endpoint).hostname
    permit = current_permit()
    if payload.get("model") != permit.model_version.partition("/")[2]:
        raise PermissionError("request model differs from outbound authorization")
    _admit_request(host)
    request = Request(
        endpoint,
        data=encoded,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            return None

    if not _in_flight.acquire(blocking=False):
        raise RuntimeError("cloud model concurrency limit reached")
    started = time.perf_counter()
    retry_count = 0
    data: bytes | None = None
    error_class: str | None = None
    invocation_id = None
    try:
        request_hash = hmac.new(api_key.encode(), encoded, hashlib.sha256).hexdigest()
        invocation_id = _record_start(endpoint, request_hash)
        for attempt in range(3):
            try:
                with build_opener(NoRedirect).open(request, timeout=90) as response:
                    data = response.read(MAX_RESPONSE_BYTES + 1)
                _transport_result(host, True)
                break
            except HTTPError as exc:
                transient = exc.code in TRANSIENT_HTTP_STATUS
                if transient and attempt < 2:
                    retry_count += 1
                    time.sleep(0.25 * (2 ** attempt))
                    continue
                if transient:
                    _transport_result(host, False)
                raise RuntimeError(f"cloud model API returned HTTP {exc.code}") from exc
            except URLError as exc:
                if attempt < 2:
                    retry_count += 1
                    time.sleep(0.25 * (2 ** attempt))
                    continue
                _transport_result(host, False)
                raise RuntimeError("cloud model API is unreachable") from exc
        if len(data) > MAX_RESPONSE_BYTES:
            raise ValueError("cloud model response exceeds size limit")
        result = json.loads(data)
        if not isinstance(result, dict):
            raise TypeError("cloud model response must be a JSON object")
        return result
    except Exception as exc:
        error_class = type(exc).__name__
        raise
    finally:
        _in_flight.release()
        if invocation_id is not None:
            output_hash = (hmac.new(api_key.encode(), data, hashlib.sha256).hexdigest()
                           if data is not None else None)
            _record_finish(invocation_id, output_hash=output_hash,
                           latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
                           retry_count=retry_count, error_class=error_class)


class CloudEmbedder:
    is_remote = True
    max_batch_size = 10

    def __init__(self, *, provider: str, model: str, endpoint: str, api_key: str):
        if provider not in {"aliyun", "siliconflow"} or not model.strip():
            raise ValueError("unsupported cloud embedding provider or model")
        self.provider = provider
        self.model = model
        self.endpoint = _checked_route(provider, "embed", endpoint)
        self.api_key = api_key
        self.model_version = f"{provider}/{model}"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        require_outbound("embed", self.model_version)
        if not texts or len(texts) > self.max_batch_size or any(not text.strip() for text in texts):
            raise ValueError("embedding batch must contain 1-10 nonempty texts")
        result = _post_json(
            self.endpoint, self.api_key,
            {"model": self.model, "input": list(texts), "encoding_format": "float"},
        )
        rows = result.get("data")
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise ValueError("embedding API returned the wrong number of rows")
        ordered = sorted(rows, key=lambda row: row["index"])
        if [row["index"] for row in ordered] != list(range(len(texts))):
            raise ValueError("embedding API returned duplicate or missing indices")
        return [[float(value) for value in row["embedding"]] for row in ordered]


class CloudReranker:
    is_remote = True
    def __init__(self, *, provider: str, model: str, endpoint: str, api_key: str):
        if provider not in {"aliyun", "siliconflow"} or not model.strip():
            raise ValueError("unsupported cloud reranking provider or model")
        self.provider = provider
        self.model = model
        self.endpoint = _checked_route(provider, "rerank", endpoint)
        self.api_key = api_key
        self.model_version = f"{provider}/{model}"

    def rerank(self, query: str, documents: Sequence[str]) -> list[tuple[int, float]]:
        require_outbound("rerank", self.model_version)
        if not query.strip() or not documents or len(documents) > 100:
            raise ValueError("reranking requires a query and 1-100 documents")
        if self.provider == "aliyun":
            payload = {
                "model": self.model,
                "input": {"query": query, "documents": list(documents)},
                "parameters": {"top_n": len(documents)},
            }
        else:
            payload = {
                "model": self.model, "query": query,
                "documents": list(documents), "top_n": len(documents),
                "return_documents": False,
            }
        result = _post_json(self.endpoint, self.api_key, payload)
        rows = result.get("output", result).get("results")
        if not isinstance(rows, list) or len(rows) != len(documents):
            raise ValueError("rerank API returned the wrong number of results")
        scores = [(int(row["index"]), float(row["relevance_score"])) for row in rows]
        if sorted(index for index, _ in scores) != list(range(len(documents))):
            raise ValueError("rerank API returned duplicate or missing document indices")
        return scores


class CloudResearchModel:
    """Cloud-only JSON completion adapter; business validation stays in ResearchService."""

    is_remote = True

    def __init__(self, *, model: str, api_key: str, provider: str = "siliconflow"):
        if not model.strip():
            raise ValueError("TCM_RESEARCH_MODEL is not configured")
        if provider not in {"siliconflow", "deepseek"}:
            raise ValueError("unsupported research model provider")
        if provider == "deepseek" and model != "deepseek-flash":
            raise ValueError("DeepSeek research route currently supports deepseek-flash only")
        self.model = model
        self.api_key = api_key
        self.provider = provider
        self.model_version = f"{provider}/{model}"
        self.endpoint = _checked_endpoint(
            "https://api.deepseek.com/chat/completions" if provider == "deepseek"
            else "https://api.siliconflow.cn/v1/chat/completions"
        )

    def complete_json_with_metadata(
        self, system_prompt: str, input_payload: dict
    ) -> tuple[dict, dict]:
        require_outbound("complete", self.model_version)
        options = (
            {"thinking": {"type": "disabled"}} if self.provider == "deepseek"
            else {"enable_thinking": False} if self.model == "Qwen/Qwen3-8B" else {}
        )
        request = {"model": self.model, "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(input_payload, ensure_ascii=False)},
        ], "response_format": {"type": "json_object"},
           "temperature": 0.2, "max_tokens": 2_048, "stream": False, **options}
        for format_attempt in range(2):
            result = _post_json(self.endpoint, self.api_key, request)
            try:
                content = result["choices"][0]["message"]["content"]
                payload = json.loads(content)
                if not isinstance(payload, dict):
                    raise TypeError("JSON completion must be an object")
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                if format_attempt == 0:
                    continue
                raise ValueError("cloud research model returned invalid JSON") from exc
            usage = result.get("usage")
            allowed = {"prompt_tokens", "completion_tokens", "total_tokens"}
            safe_usage = {key: value for key, value in usage.items()
                          if key in allowed and type(value) is int and value >= 0} \
                if isinstance(usage, dict) else {}
            if format_attempt:
                safe_usage["format_retry_count"] = format_attempt
            return payload, safe_usage
        raise AssertionError("unreachable completion retry state")

    def complete_json(self, system_prompt: str, input_payload: dict) -> dict:
        return self.complete_json_with_metadata(system_prompt, input_payload)[0]


def _credential(provider: str) -> str:
    """Read OS keychain; injected env keys require an explicit development switch."""
    try:
        key = read_model_key(provider)
    except (OSError, RuntimeError) as exc:
        if os.getenv("TCM_ALLOW_ENV_API_KEYS") != "1":
            raise RuntimeError("OS keychain is unavailable for model credentials") from exc
        key = None
    if key:
        return key
    if os.getenv("TCM_ALLOW_ENV_API_KEYS") == "1":
        key_name = {"deepseek": "DEEPSEEK_API_KEY", "siliconflow": "SILICONFLOW_API_KEY",
                    "aliyun": "DASHSCOPE_API_KEY"}[provider]
        key = os.getenv(key_name, "")
        if key:
            return key
    raise ValueError(f"{provider} model credential is not configured in OS keychain")


def research_model_from_environment() -> CloudResearchModel:
    provider = os.getenv("TCM_RESEARCH_PROVIDER", "siliconflow").lower()
    if provider not in {"siliconflow", "deepseek"}:
        raise ValueError("TCM_RESEARCH_PROVIDER must be siliconflow or deepseek")
    key = _credential(provider)
    return CloudResearchModel(
        model=os.getenv("TCM_RESEARCH_MODEL", ""), api_key=key, provider=provider,
    )


def research_model_for_version(model_version: str) -> CloudResearchModel:
    provider, sep, model = model_version.partition("/")
    if not sep or provider not in {"siliconflow", "deepseek"}:
        raise ValueError("frozen research model route is unsupported")
    key = _credential(provider)
    return CloudResearchModel(model=model, api_key=key, provider=provider)


def cloud_clients_from_environment() -> tuple[CloudEmbedder, CloudReranker]:
    provider = os.getenv("TCM_MODEL_PROVIDER", "siliconflow").lower()
    if provider == "aliyun":
        workspace = os.getenv("TCM_DASHSCOPE_WORKSPACE_ID", "")
        region = os.getenv("TCM_DASHSCOPE_REGION", "cn-beijing")
        if not WORKSPACE.fullmatch(workspace) or not WORKSPACE.fullmatch(region):
            raise ValueError("DashScope workspace ID and region must be configured")
        host = f"https://{workspace}.{region}.maas.aliyuncs.com"
        key = _credential(provider)
        return (
            CloudEmbedder(
                provider="aliyun",
                model=os.getenv("TCM_EMBEDDING_MODEL", "qwen3.7-text-embedding"),
                endpoint=f"{host}/compatible-mode/v1/embeddings", api_key=key,
            ),
            CloudReranker(
                provider="aliyun",
                model=os.getenv("TCM_RERANK_MODEL", "qwen3.7-text-rerank"),
                endpoint=f"{host}/api/v1/services/rerank/text-rerank/text-rerank",
                api_key=key,
            ),
        )
    if provider == "siliconflow":
        key = _credential(provider)
        return (
            CloudEmbedder(
                provider="siliconflow",
                model=os.getenv("TCM_EMBEDDING_MODEL", "BAAI/bge-m3"),
                endpoint="https://api.siliconflow.cn/v1/embeddings", api_key=key,
            ),
            CloudReranker(
                provider="siliconflow",
                model=os.getenv("TCM_RERANK_MODEL", "BAAI/bge-reranker-v2-m3"),
                endpoint="https://api.siliconflow.cn/v1/rerank", api_key=key,
            ),
        )
    raise ValueError("TCM_MODEL_PROVIDER must be aliyun or siliconflow")
