"""Small, versioned documentation corpus with BM25 and optional local embeddings.

Only published articles in the explicit allowlist are indexed. Source code,
old reviews, credentials and arbitrary files are never ingested.
"""

import hashlib
import json
import logging
import math
import os
import re
import tempfile
import threading
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from app.config import Settings
from app.core.errors import BusinessException
from app.core.permissions import ROLE_PERMISSIONS
from app.modules.assistant.provider import Ollama
from app.modules.assistant.schemas import Source
from app.schemas.errors import ErrorCode

logger = logging.getLogger("rtk.assistant")

ARTICLES = {
    **{f"user-guide/{slug}.md": None for slug in (
        "getting-started", "overview", "universities", "passport", "programs-products",
        "workflow", "comments-files", "documents", "reports", "history",
    )},
    "help/faq.md": None,
    "help/health-score.md": None,
    "roles/user.md": None,
    "roles/manager.md": "analytics.extended",
    "roles/admin.md": "admin.users",
    "admin-guide/catalogs.md": "university.edit",
    "admin-guide/import.md": "import.write",
    "admin-guide/users.md": "admin.users",
    "admin-guide/workflow-templates.md": "workflow_template.manage",
}
STOP_WORDS = {
    "как", "где", "что", "это", "или", "для", "при", "мне", "меня", "нужно", "хочу",
    "можно", "почему", "когда", "какой", "какие", "есть", "про", "пожалуйста", "чем",
    "этом", "эту", "если", "через", "после", "перед", "чтобы", "должен", "будет",
    "сделать", "узнать", "подскажи", "расскажи",
}


def tokens(value: str) -> list[str]:
    words = re.findall(r"[a-zа-яё0-9]+", value.lower().replace("ё", "е"))
    return [word[:6] if re.search("[а-я]", word) else word
            for word in words if len(word) >= 3 and word not in STOP_WORDS]


def expand_query(query: str) -> str:
    groups = (
        (r"воркф|workflow|откат|верну|возврат", "workflow этап переход возврат"),
        (r"ексел|эксел|excel|xlsx", "excel импорт справочников"),
        (r"выгруз|экспорт", "отчёт скачать экспорт"),
        (r"доступ|авториз|войти|вход", "вход доступ пользователь права"),
    )
    return query + " " + " ".join(words for pattern, words in groups
                                  if re.search(pattern, query, re.IGNORECASE))


@dataclass(frozen=True)
class Chunk:
    id: str
    article_id: str
    title: str
    url: str
    text: str
    permission: str | None

    def source(self) -> Source:
        return Source(id=self.id, title=self.title, url=self.url, excerpt=self.text[:600])


@dataclass(frozen=True)
class Snapshot:
    version: str
    document_count: int
    chunks: tuple[Chunk, ...]
    embeddings: dict[str, list[float]]

    def visible(self, role: str) -> list[Chunk]:
        permissions = ROLE_PERMISSIONS.get(role, frozenset())
        return [chunk for chunk in self.chunks
                if chunk.permission is None or chunk.permission in permissions]


def _sections(body: str, size: int = 1200) -> list[str]:
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)
    sections = re.split(r"(?=^#{1,6} )", body, flags=re.MULTILINE)
    result = []
    for section in sections:
        section = section.strip()
        while section:
            end = min(len(section), size)
            if end < len(section):
                boundary = section.rfind("\n", size // 2, end)
                if boundary == -1:
                    boundary = section.rfind(" ", size // 2, end)
                if boundary > 0:
                    end = boundary
            piece = section[:end].strip()
            if piece:
                result.append(piece)
            section = section[end:].strip()
    return result


class KnowledgeBase:
    def __init__(self, root: Path, index_path: Path, embedding_model: str):
        self.root = root.resolve()
        self.index_path = index_path
        self.embedding_model = embedding_model
        self._lock = threading.Lock()
        self._signature: tuple = ()
        self._snapshot: Snapshot | None = None

    def snapshot(self) -> Snapshot:
        with self._lock:
            signature = []
            for relative in ARTICLES:
                path = (self.root / relative).resolve()
                if not path.is_relative_to(self.root) or not path.is_file():
                    continue
                stat = path.stat()
                signature.append((relative, stat.st_mtime_ns, stat.st_size))
            if self.index_path.is_file():
                stat = self.index_path.stat()
                signature.append(("index", stat.st_mtime_ns, stat.st_size))
            key = tuple(signature)
            if self._snapshot is not None and key == self._signature:
                return self._snapshot
            chunks = []
            digest = hashlib.sha256(b"assistant-knowledge-v1")
            documents = 0
            for relative, _, size in signature:
                if relative == "index" or size > 96_000:
                    continue
                source = (self.root / relative).read_text(encoding="utf-8")
                digest.update(relative.encode())
                digest.update(source.encode())
                metadata = {}
                match = re.match(r"\A---\s*\n(.*?)\n---\s*\n?", source, re.DOTALL)
                if match:
                    for line in match[1].splitlines():
                        if ":" in line:
                            name, value = line.split(":", 1)
                            metadata[name.strip()] = value.strip().strip("\"'")
                    source = source[match.end():]
                section = metadata.get("section", relative.split("/")[0])
                slug = metadata.get("slug", Path(relative).stem)
                if not re.fullmatch(r"[a-z-]+/[a-z-]+", f"{section}/{slug}"):
                    continue
                article_id = f"{section}/{slug}"
                title = metadata.get("title", slug)
                pieces = _sections(source)
                if not pieces:
                    continue
                documents += 1
                for position, piece in enumerate(pieces):
                    identifier = hashlib.sha256(f"{relative}:{position}".encode()).hexdigest()[:16]
                    chunks.append(Chunk(
                        identifier, article_id, title,
                        f"/docs?article={quote(article_id, safe='')}",
                        piece, ARTICLES[relative],
                    ))
            version = digest.hexdigest()
            embeddings = self._read_embeddings(version, chunks)
            self._snapshot = Snapshot(version, documents, tuple(chunks), embeddings)
            self._signature = key
            return self._snapshot

    def _read_embeddings(self, version: str, chunks: list[Chunk]) -> dict[str, list[float]]:
        if not self.index_path.is_file() or self.index_path.stat().st_size > 16_000_000:
            return {}
        try:
            stored = json.loads(self.index_path.read_text(encoding="utf-8"))
            if stored["version"] != version or stored["model"] != self.embedding_model:
                return {}
            vectors = stored["vectors"]
            if not isinstance(vectors, dict) or set(vectors) != {chunk.id for chunk in chunks}:
                return {}
            dimension = None
            for vector in vectors.values():
                if not isinstance(vector, list) or not 32 <= len(vector) <= 4096:
                    return {}
                if dimension not in {None, len(vector)}:
                    return {}
                dimension = len(vector)
                if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in vector):
                    return {}
                if not 0.99 <= sum(x * x for x in vector) <= 1.01:
                    return {}
            return vectors
        except (OSError, ValueError, TypeError, KeyError):
            logger.warning("assistant embedding index unreadable; using lexical retrieval")
            return {}

    def build_embeddings(self, provider: Ollama) -> Snapshot:
        snapshot = self.snapshot()
        if not snapshot.chunks:
            raise BusinessException(ErrorCode.ASSISTANT_KNOWLEDGE_UNAVAILABLE)
        vectors = {}
        for start in range(0, len(snapshot.chunks), 8):
            batch = snapshot.chunks[start:start + 8]
            values = provider.embed([f"{chunk.title}\n{chunk.text}" for chunk in batch])
            vectors.update((chunk.id, vector) for chunk, vector in zip(batch, values, strict=True))
        payload = {"version": snapshot.version, "model": self.embedding_model, "vectors": vectors}
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.index_path.parent, delete=False
            ) as handle:
                temporary = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False, allow_nan=False)
            os.replace(temporary, self.index_path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return self.snapshot()


def lexical_ranking(query: str, chunks: list[Chunk]) -> list[tuple[Chunk, float]]:
    terms = set(tokens(expand_query(query)))
    documents = [Counter(tokens(f"{chunk.title} {chunk.title}\n{chunk.text}"))
                 for chunk in chunks]
    average = sum(sum(doc.values()) for doc in documents) / max(len(documents), 1)
    ranked = []
    for chunk, document in zip(chunks, documents, strict=True):
        score = 0.0
        length = sum(document.values())
        for term in terms:
            frequency = document[term]
            if not frequency:
                continue
            containing = sum(term in doc for doc in documents)
            idf = math.log(1 + (len(documents) - containing + 0.5) / (containing + 0.5))
            score += idf * frequency * 2.2 / (
                frequency + 1.2 * (0.25 + 0.75 * length / max(average, 1))
            )
        if score >= 0.5:
            ranked.append((chunk, score))
    return sorted(ranked, key=lambda item: (-item[1], item[0].id))


def retrieve(
    snapshot: Snapshot, query: str, role: str, provider: Ollama
) -> tuple[list[Chunk], str]:
    chunks = snapshot.visible(role)
    lexical = lexical_ranking(query, chunks)
    ranks = {chunk.id: 1 / (60 + i) for i, (chunk, _) in enumerate(lexical, 1)}
    mode = "lexical"
    if snapshot.embeddings and chunks:
        try:
            query_vector = provider.embed([
                ("Instruct: Retrieve CRM documentation relevant to the user's question.\n"
                 f"Query: {query}")
            ])[0]
            semantic = []
            for chunk in chunks:
                vector = snapshot.embeddings[chunk.id]
                if len(query_vector) != len(vector):
                    raise ValueError("Embedding dimension changed")
                cosine = sum(a * b for a, b in zip(query_vector, vector, strict=True))
                if cosine >= 0.45:
                    semantic.append((chunk, cosine))
            semantic.sort(key=lambda item: (-item[1], item[0].id))
            for i, (chunk, _) in enumerate(semantic, 1):
                ranks[chunk.id] = ranks.get(chunk.id, 0) + 1 / (60 + i)
            mode = "hybrid"
        except (BusinessException, ValueError):
            logger.warning("assistant query embedding unavailable; using lexical retrieval")
    result = []
    article_counts: Counter = Counter()
    for chunk in sorted(chunks, key=lambda item: (-ranks.get(item.id, 0), item.id)):
        if chunk.id not in ranks or article_counts[chunk.article_id] >= 2:
            continue
        result.append(chunk)
        article_counts[chunk.article_id] += 1
        if len(result) == 4:
            break
    return result, mode


@lru_cache(maxsize=4)
def _knowledge(root: str, index_path: str, embedding_model: str) -> KnowledgeBase:
    return KnowledgeBase(Path(root), Path(index_path), embedding_model)


def get_knowledge(config: Settings) -> KnowledgeBase:
    return _knowledge(config.assistant_docs_root, config.assistant_index_path,
                      config.assistant_embedding_model)
