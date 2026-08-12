from archivum.retrieval.hybrid import fuse_ranked_hits


def test_fuse_ranked_hits_prefers_items_found_by_multiple_channels():
    hits = fuse_ranked_hits(
        keyword=[("page:a", 0.7), ("page:b", 0.9)],
        vector=[("page:a", 0.8), ("page:c", 0.95)],
        graph=[("page:a", 0.4)],
        limit=2,
    )

    assert [hit.id for hit in hits] == ["page:a", "page:b"]
    assert hits[0].score > hits[1].score
