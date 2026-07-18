from app.config import settings

from .bge_m3 import cosine_similarity, sparse_dot_product

if settings.EMBEDDING_PROVIDER == "gemini":
    from .gemini_embed import embed_single, embed_texts
elif settings.EMBEDDING_PROVIDER == "bge_m3_cloud":
    from .bge_m3_cloud import embed_single, embed_texts
else:
    from .bge_m3 import embed_single, embed_texts

__all__ = ["embed_texts", "embed_single", "cosine_similarity", "sparse_dot_product"]
