"""Knowledge retrieval helpers for country-specific references."""

from pathlib import Path
from typing import List

from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings

from config import CHROMA_PERSIST_DIR, EMBEDDING_MODEL, OPENAI_API_BASE, OPENAI_API_KEY


class CountryKnowledgeRetriever:
    """Load country knowledge with vector-search-first and text fallback."""

    def __init__(self, country: str):
        normalized_country = country.strip().lower()
        self.country = normalized_country
        self.data_file = Path("knowledge") / "data" / f"{normalized_country}.txt"
        self.vector_dir = Path(CHROMA_PERSIST_DIR) / normalized_country

        if not self.data_file.exists():
            available = ", ".join(self.available_countries()) or "(none)"
            raise ValueError(
                f"Knowledge file not found: {self.data_file}. "
                f"Available countries: {available}"
            )

        self._fallback_text = self.data_file.read_text(encoding="utf-8")

    @staticmethod
    def available_countries() -> List[str]:
        return sorted(path.stem for path in (Path("knowledge") / "data").glob("*.txt"))

    def get_reference(self, query: str, *, max_chars: int = 2800, top_k: int = 4) -> str:
        """Return best knowledge reference for a query."""
        vector_reference = self._query_vector_store(query=query, top_k=top_k)
        if vector_reference:
            return vector_reference[:max_chars]

        if len(self._fallback_text) <= max_chars:
            return self._fallback_text
        return f"{self._fallback_text[:max_chars]}..."

    def _query_vector_store(self, query: str, top_k: int) -> str:
        if not (self.vector_dir / "chroma.sqlite3").exists():
            return ""

        try:
            embeddings = OpenAIEmbeddings(
                model=EMBEDDING_MODEL,
                openai_api_key=OPENAI_API_KEY,
                base_url=OPENAI_API_BASE,
            )
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
        for doc in docs:
            text = " ".join(doc.page_content.split())
            if text and text not in cleaned:
                cleaned.append(text)

        return "\n".join(cleaned)
