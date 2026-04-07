import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


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

            clusters.append({
                "pages": [pages[idx] for idx in cluster],
                "avg_similarity": round(avg_sim, 3),
            })

    print("Cluster sizes:", [len(c["pages"]) for c in clusters])
    print("Cluster types:", [set(p.get("type") for p in c["pages"]) for c in clusters])
    return clusters
