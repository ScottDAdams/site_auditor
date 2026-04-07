from urllib.parse import urlparse

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


def _assign_cluster_urls(cluster):
    """
    Single canonical URL per cluster (shallowest path), remainder as competing URLs.
    """
    pages = cluster.get("pages") or []
    if not pages:
        cluster["dominant_url"] = None
        cluster["competing_urls"] = []
        return
    if len(pages) == 1:
        u = pages[0]["url"]
        cluster["dominant_url"] = u
        cluster["competing_urls"] = []
        return
    scored = []
    for p in pages:
        url = p["url"]
        path = p.get("path")
        if path is None:
            path = urlparse(url).path
        depth = len([x for x in (path or "").strip("/").split("/") if x])
        scored.append((depth, len(url), url))
    scored.sort(key=lambda x: (x[0], x[1], x[2]))
    dom = scored[0][2]
    comp = [t[2] for t in scored[1:]]
    cluster["dominant_url"] = dom
    cluster["competing_urls"] = comp


def cluster_pages(pages, embeddings, threshold=0.89):
    if not pages:
        return []

    sim_matrix = cosine_similarity(embeddings)
    n = len(pages)

    clusters = []
    used = set()

    for i in range(n):
        if i in used:
            continue

        cluster = [i]

        for j in range(n):
            if i == j or j in used:
                continue

            # Require mutual similarity with ALL current cluster members
            if all(sim_matrix[j][k] > threshold for k in cluster):
                cluster.append(j)

        if len(cluster) > 1:
            for idx in cluster:
                used.add(idx)

            sims = [
                sim_matrix[a][b]
                for a in cluster for b in cluster
                if a != b
            ]
            avg_sim = float(np.mean(sims)) if sims else 0

            c_obj = {
                "pages": [pages[idx] for idx in cluster],
                "avg_similarity": round(avg_sim, 3),
            }
            _assign_cluster_urls(c_obj)
            clusters.append(c_obj)

    print("Cluster sizes:", [len(c["pages"]) for c in clusters])
    print("Cluster types:", [set(p.get("type") for p in c["pages"]) for c in clusters])
    return clusters
