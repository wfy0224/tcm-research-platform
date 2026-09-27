"""Cloud embedding and reranking adapters; credentials come only from environment."""

import json
import os
import re
from collections.abc import Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_RESPONSE_BYTES = 16 * 1024 * 1024
WORKSPACE = re.compile(r"^[a-zA-Z0-9-]{1,100}$")


def _checked_endpoint(url: str) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.hostname is None
        or not (
            parsed.hostname == "api.siliconflow.cn"
            or parsed.hostname.endswith(".maas.aliyuncs.com")
        )
    ):
        raise ValueError("model endpoint must be an approved HTTPS provider host")
    return url


def _post_json(url: str, api_key: str, payload: dict) -> dict:
    if not api_key:
        raise ValueError("cloud model API key is not configured")
    request = Request(
        _checked_endpoint(url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
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

    try:
        with build_opener(NoRedirect).open(request, timeout=90) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raise RuntimeError(f"cloud model API returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("cloud model API is unreachable") from exc
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("cloud model response exceeds size limit")
    result = json.loads(data)
    if not isinstance(result, dict):
        raise TypeError("cloud model response must be a JSON object")
    return result


class CloudEmbedder:
    max_batch_size = 10

    def __init__(self, *, provider: str, model: str, endpoint: str, api_key: str):
        if provider not in {"aliyun", "siliconflow"} or not model.strip():
            raise ValueError("unsupported cloud embedding provider or model")
        self.provider = provider
        self.model = model
        self.endpoint = _checked_endpoint(endpoint)
        self.api_key = api_key
        self.model_version = f"{provider}/{model}"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
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
    def __init__(self, *, provider: str, model: str, endpoint: str, api_key: str):
        if provider not in {"aliyun", "siliconflow"} or not model.strip():
            raise ValueError("unsupported cloud reranking provider or model")
        self.provider = provider
        self.model = model
        self.endpoint = _checked_endpoint(endpoint)
        self.api_key = api_key
        self.model_version = f"{provider}/{model}"

    def rerank(self, query: str, documents: Sequence[str]) -> list[tuple[int, float]]:
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

    def __init__(self, *, model: str, api_key: str):
        if not model.strip():
            raise ValueError("TCM_RESEARCH_MODEL is not configured")
        self.model = model
        self.api_key = api_key
        self.model_version = f"siliconflow/{model}"

    def complete_json(self, system_prompt: str, input_payload: dict) -> dict:
        options = {"enable_thinking": False} if self.model == "Qwen/Qwen3-8B" else {}
        result = _post_json(
            "https://api.siliconflow.cn/v1/chat/completions", self.api_key,
            {"model": self.model, "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(input_payload, ensure_ascii=False)},
            ], "response_format": {"type": "json_object"},
             "temperature": 0.2, "max_tokens": 2_048, "stream": False, **options},
        )
        try:
            content = result["choices"][0]["message"]["content"]
            payload = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("cloud research model returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise TypeError("cloud research model must return a JSON object")
        return payload


def research_model_from_environment() -> CloudResearchModel:
    if os.getenv("TCM_MODEL_PROVIDER", "siliconflow").lower() != "siliconflow":
        raise ValueError("research generation currently supports SiliconFlow cloud API")
    key = os.getenv("SILICONFLOW_API_KEY", "")
    if not key:
        raise ValueError("SILICONFLOW_API_KEY is not configured")
    return CloudResearchModel(model=os.getenv("TCM_RESEARCH_MODEL", ""), api_key=key)


def cloud_clients_from_environment() -> tuple[CloudEmbedder, CloudReranker]:
    provider = os.getenv("TCM_MODEL_PROVIDER", "siliconflow").lower()
    if provider == "aliyun":
        workspace = os.getenv("TCM_DASHSCOPE_WORKSPACE_ID", "")
        region = os.getenv("TCM_DASHSCOPE_REGION", "cn-beijing")
        if not WORKSPACE.fullmatch(workspace) or not WORKSPACE.fullmatch(region):
            raise ValueError("DashScope workspace ID and region must be configured")
        host = f"https://{workspace}.{region}.maas.aliyuncs.com"
        key = os.getenv("DASHSCOPE_API_KEY", "")
        if not key:
            raise ValueError("DASHSCOPE_API_KEY is not configured")
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
        key = os.getenv("SILICONFLOW_API_KEY", "")
        if not key:
            raise ValueError("SILICONFLOW_API_KEY is not configured")
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
