"""Knowledge retrieval helpers for country-specific references."""

from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime
from functools import lru_cache

from config import CHROMA_PERSIST_DIR, EMBEDDING_MODEL, LLM_API_BASE, LLM_API_KEY
from urllib.parse import urlparse


def _base_candidates() -> list[str]:
    base = (LLM_API_BASE or "").strip().rstrip("/")
    if not base:
        return [""]
    parsed = urlparse(base)
    needs_v1 = (parsed.path in ("", "/")) and not base.endswith("/v1")
    if needs_v1:
        return [f"{base}/v1", base]
    candidates = [base]
    if not base.endswith("/v1"):
        candidates.append(f"{base}/v1")
    return candidates


@lru_cache(maxsize=1)
def _create_embeddings() -> "OpenAIEmbeddings":
    """Create OpenAIEmbeddings with compatibility across langchain-openai versions."""
    from langchain_openai import OpenAIEmbeddings

    last_exc = None
    for base in _base_candidates():
        try:
            return OpenAIEmbeddings(
                model=EMBEDDING_MODEL,
                openai_api_key=LLM_API_KEY,
                base_url=base or None,
            )
        except Exception as exc:
            last_exc = exc
            msg = str(exc).lower()
            if "base_url" not in msg and "extra fields" not in msg:
                break

    for base in _base_candidates():
        try:
            return OpenAIEmbeddings(
                model=EMBEDDING_MODEL,
                openai_api_key=LLM_API_KEY,
                openai_api_base=base or None,
            )
        except Exception as exc:
            last_exc = exc

    assert last_exc is not None
    raise last_exc


@lru_cache(maxsize=64)
def _load_knowledge_file_cached(path_str: str, mtime: float) -> Tuple[Dict[str, str], str]:
    path = Path(path_str)
    return load_knowledge_file(path)


def _data_dir_mtime() -> float:
    try:
        return (Path("knowledge") / "data").stat().st_mtime
    except Exception:
        return 0.0


@lru_cache(maxsize=1)
def _available_countries_cached(_: float) -> List[str]:
    return sorted(path.stem for path in (Path("knowledge") / "data").glob("*.txt"))


def load_knowledge_file(path: Path) -> Tuple[Dict[str, str], str]:
    """Load knowledge file with optional metadata header lines starting with '#'."""
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    meta: Dict[str, str] = {}
    idx = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            payload = stripped.lstrip("#").strip()
            if ":" in payload:
                key, value = payload.split(":", 1)
                meta[key.strip().lower()] = value.strip()
            idx += 1
            continue
        if stripped == "" and idx == 0:
            idx += 1
            continue
        break
    content = "\n".join(lines[idx:]).strip()
    return meta, content


class CountryKnowledgeRetriever:
    """Load country knowledge with vector-search-first and text fallback."""

    def __init__(self, country: str):
        normalized_country = country.strip().lower()
        if not normalized_country:
            raise ValueError("Target market cannot be empty.")
        if any(token in normalized_country for token in ("/", "\\", "..", ":", "\u0000")):
            raise ValueError(
                "Invalid target market. Please avoid '/', '\\\\', '..', ':', or null bytes."
            )
        self.country = normalized_country
        self.data_file = Path("knowledge") / "data" / f"{normalized_country}.txt"
        self.vector_dir = Path(CHROMA_PERSIST_DIR) / normalized_country
        self._fallback_text = ""
        self.metadata: Dict[str, str] = {}
        self.version_tag = "missing"
        if self.data_file.exists():
            try:
                mtime = self.data_file.stat().st_mtime
                mtime_tag = datetime.utcfromtimestamp(mtime).strftime("%Y%m%d%H%M%S")
            except Exception:
                mtime_tag = "unknown"
                mtime = 0.0
            self.metadata, self._fallback_text = _load_knowledge_file_cached(
                str(self.data_file), float(mtime)
            )
            last_updated = self.metadata.get("last_updated")
            if last_updated:
                self.version_tag = f"{last_updated}-{mtime_tag}"
            else:
                self.version_tag = mtime_tag

    @staticmethod
    def available_countries() -> List[str]:
        return _available_countries_cached(_data_dir_mtime())

    def get_reference(self, query: str, *, max_chars: int = 2800, top_k: int = 4) -> str:
        """Return best knowledge reference for a query."""
        vector_reference = self._query_vector_store(query=query, top_k=top_k)
        if vector_reference:
            parts = [f"{key}={value}" for key, value in self.metadata.items() if value]
            if self.version_tag:
                parts.append(f"version={self.version_tag}")
            meta_prefix = "Metadata: " + "; ".join(parts) + "\n" if parts else ""
            combined = f"{meta_prefix}{vector_reference}".strip()
            return combined[:max_chars]

        if self._fallback_text:
            parts = [f"{key}={value}" for key, value in self.metadata.items() if value]
            if self.version_tag:
                parts.append(f"version={self.version_tag}")
            meta_prefix = "Metadata: " + "; ".join(parts) + "\n" if parts else ""
            combined = f"{meta_prefix}{self._fallback_text}".strip()
            if len(combined) <= max_chars:
                return combined
            return f"{combined[:max_chars]}..."

        return (
            f"No local knowledge file found for '{self.country}'. "
            "Answer using general knowledge and flag items that need verification."
        )[:max_chars]

    def _query_vector_store(self, query: str, top_k: int) -> str:
        if not (self.vector_dir / "chroma.sqlite3").exists():
            return ""

        if not LLM_API_KEY:
            return ""

        try:
            from langchain_community.vectorstores import Chroma

            embeddings = _create_embeddings()
            vector_store = Chroma(
                persist_directory=str(self.vector_dir),
                embedding_function=embeddings,
            )
            docs = vector_store.similarity_search(query, k=top_k)
        except Exception as exc:
            print(f"[warning] Vector retrieval failed for '{self.country}': {exc}")
            return ""

        if not docs:
            return ""

        cleaned = []
        seen = set()
        for doc in docs:
            text = " ".join(doc.page_content.split())
            if text and text not in seen:
                seen.add(text)
                cleaned.append(text)

        return "\n".join(cleaned)
