"""
Elasticsearch integration (disabled — ES not reachable).
All functions are safe no-ops. To enable, set ES_ENABLED=true in .env
and ensure ES is reachable at ES_HOST.
"""

from config import settings

ES_ENABLED = settings.ES_HOST and getattr(settings, "ES_ENABLED", False)
es = None

if ES_ENABLED:
    try:
        from elasticsearch import Elasticsearch
        es = Elasticsearch(settings.ES_HOST)
        es.info()  # test connection
        print(f"[ES] Connected to {settings.ES_HOST}")
    except Exception as e:
        print(f"[ES] Disabled — cannot connect: {e}")
        ES_ENABLED = False
        es = None


def ensure_index():
    if not ES_ENABLED:
        return


def index_image(**kwargs):
    if not ES_ENABLED:
        return


def search_images(query, folder=None, tag=None, category=None, page=1, page_size=48):
    raise RuntimeError("ES not enabled")


def delete_image(image_id):
    pass


def reindex_all(db_session):
    return 0
