import os
import time

import chromadb

from urbanstream.llm_config import CHROMA_PERSIST_DIR, RAG_TOP_K

COLLECTIONS = ("chat_history", "stream_events", "knowledge", "user_profiles")


class RAGStore:
    def __init__(self, persist_dir=None, embed_fn=None):
        path = persist_dir or CHROMA_PERSIST_DIR
        self._client = chromadb.PersistentClient(path=path)
        self._embed_fn = embed_fn  # sync callable: str -> list[float]
        self._cols = {}
        for name in COLLECTIONS:
            self._cols[name] = self._client.get_or_create_collection(
                name=name, metadata={"hnsw:space": "cosine"}
            )

    def _embed(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        return [self._embed_fn(t) for t in texts]

    def ingest_chat(self, username, text, is_streamer=False):
        doc_id = f"chat-{username}-{time.time()}"
        self._cols["chat_history"].add(
            ids=[doc_id],
            documents=[text],
            embeddings=self._embed(text),
            metadatas=[{
                "username": username,
                "is_streamer": is_streamer,
                "timestamp": time.time(),
            }],
        )

    def ingest_event(self, event_type, description):
        doc_id = f"event-{event_type}-{time.time()}"
        self._cols["stream_events"].add(
            ids=[doc_id],
            documents=[description],
            embeddings=self._embed(description),
            metadatas=[{"event_type": event_type, "timestamp": time.time()}],
        )

    def ingest_knowledge(self, doc_id, text):
        self._cols["knowledge"].upsert(
            ids=[doc_id],
            documents=[text],
            embeddings=self._embed(text),
            metadatas=[{"source": doc_id, "timestamp": time.time()}],
        )

    def update_user_profile(self, username, summary):
        doc_id = f"profile-{username}"
        self._cols["user_profiles"].upsert(
            ids=[doc_id],
            documents=[summary],
            embeddings=self._embed(summary),
            metadatas=[{"username": username, "timestamp": time.time()}],
        )

    def retrieve(self, query, top_k=None, collections=None):
        top_k = top_k or RAG_TOP_K
        cols_to_search = collections or list(COLLECTIONS)
        results = []
        query_emb = self._embed(query)
        for col_name in cols_to_search:
            col = self._cols.get(col_name)
            if not col or col.count() == 0:
                continue
            k = min(top_k, col.count())
            hits = col.query(query_embeddings=query_emb, n_results=k)
            for i, doc in enumerate(hits["documents"][0]):
                dist = hits["distances"][0][i] if hits.get("distances") else 1.0
                meta = hits["metadatas"][0][i] if hits.get("metadatas") else {}
                results.append({
                    "text": doc,
                    "distance": dist,
                    "collection": col_name,
                    "metadata": meta,
                })
        results.sort(key=lambda r: r["distance"])
        return results[:top_k]

    def get_user_profile(self, username):
        doc_id = f"profile-{username}"
        try:
            result = self._cols["user_profiles"].get(ids=[doc_id])
            if result["documents"]:
                return result["documents"][0]
        except Exception:
            pass
        return None

    def load_knowledge_dir(self, dir_path):
        if not os.path.isdir(dir_path):
            print(f"[RAG] Knowledge directory not found: {dir_path}")
            return 0
        count = 0
        for fname in os.listdir(dir_path):
            if not fname.endswith((".txt", ".md")):
                continue
            fpath = os.path.join(dir_path, fname)
            with open(fpath, encoding="utf-8") as f:
                text = f.read().strip()
            if text:
                self.ingest_knowledge(fname, text)
                count += 1
                print(f"[RAG] Loaded knowledge: {fname}")
        return count
