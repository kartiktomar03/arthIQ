from typing import Protocol


class Embedder(Protocol):
    identity: str

    def encode(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingUnavailable(RuntimeError):
    pass


class MiniLMEmbedder:
    identity = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self, local_files_only: bool = False):
        self.local_files_only = local_files_only
        self.model = None

    def encode(self, texts: list[str]) -> list[list[float]]:
        try:
            if self.model is None:
                import torch
                from sentence_transformers import SentenceTransformer

                torch.set_num_threads(2)
                self.model = SentenceTransformer(
                    self.identity, device="cpu", local_files_only=self.local_files_only,
                    trust_remote_code=False,
                )
            return self.model.encode(texts, batch_size=16, normalize_embeddings=True).tolist()
        except (ImportError, OSError, RuntimeError, ValueError):
            raise EmbeddingUnavailable(
                "The CPU embedding model is unavailable. Check the RAG installation and model cache."
            ) from None
