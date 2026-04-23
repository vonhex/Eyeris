"""
Image indexing helpers — currently no-ops.
Full-text search uses SearXNG; add a real backend when needed.
"""

def ensure_index():
    """No-op — ES removed in favor of SearXNG search."""


def index_image(**kwargs):
    """No-op — ES removed in favor of SearXNG search."""


def search_images(query, folder=None, tag=None, category=None, page=1, page_size=48):
    """No-op — ES removed in favor of SearXNG search."""
    return {"results": [], "total": 0}


def delete_image(image_id):
    pass


def reindex_all(db_session):
    return 0
