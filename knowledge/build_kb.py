"""Build country knowledge vector stores from text files."""

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from langchain.text_splitter import CharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings

from config import CHROMA_PERSIST_DIR, EMBEDDING_MODEL, OPENAI_API_BASE, OPENAI_API_KEY, validate_required_config


def build_knowledge_base(country_code: str, file_path: str, chunk_size: int, chunk_overlap: int) -> None:
    loader = TextLoader(file_path, encoding="utf-8")
    documents = loader.load()

    text_splitter = CharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    docs = text_splitter.split_documents(documents)

    embeddings = OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        openai_api_key=OPENAI_API_KEY,
        base_url=OPENAI_API_BASE,
    )

    persist_dir = Path(CHROMA_PERSIST_DIR) / country_code
    if persist_dir.exists():
        shutil.rmtree(persist_dir)
    persist_dir.parent.mkdir(parents=True, exist_ok=True)

    vectordb = Chroma.from_documents(
        docs,
        embeddings,
        persist_directory=str(persist_dir),
    )
    vectordb.persist()
    print(f"Knowledge base built: {country_code}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Chroma knowledge base for toy localization.")
    parser.add_argument(
        "--country",
        help="Optional country code (e.g., japan). If omitted, build all *.txt under data dir.",
    )
    parser.add_argument(
        "--data-dir",
        default=str(Path(__file__).parent / "data"),
        help="Directory containing country txt files.",
    )
    parser.add_argument("--chunk-size", type=int, default=200, help="Chunk size for text splitting.")
    parser.add_argument("--chunk-overlap", type=int, default=20, help="Chunk overlap for text splitting.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    validate_required_config(skip_vision=True)

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory does not exist: {data_dir}")

    if args.country:
        country = args.country.strip().lower()
        source_file = data_dir / f"{country}.txt"
        if not source_file.exists():
            available = ", ".join(sorted(path.stem for path in data_dir.glob("*.txt"))) or "(none)"
            raise FileNotFoundError(
                f"Country file not found: {source_file}. Available countries: {available}"
            )
        build_knowledge_base(country, str(source_file), args.chunk_size, args.chunk_overlap)
    else:
        txt_files = sorted(data_dir.glob("*.txt"))
        if not txt_files:
            raise RuntimeError(f"No txt files found in data directory: {data_dir}")

        for source_file in txt_files:
            country = source_file.stem
            build_knowledge_base(country, str(source_file), args.chunk_size, args.chunk_overlap)
