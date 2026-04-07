from sklearn.metrics.pairwise import cosine_similarity

def cluster_pages(pages, embeddings, threshold=0.85):
    clusters = []
    used = set()

    for i, emb in enumerate(embeddings):
        if i in used:
            continue

        cluster = [i]

        for j in range(i + 1, len(embeddings)):
            if j in used:
                continue

            sim = cosine_similarity([emb], [embeddings[j]])[0][0]

            if sim > threshold:
                cluster.append(j)
                used.add(j)

        if len(cluster) > 1:
            clusters.append({
                "pages": [pages[idx] for idx in cluster],
                "similarity": round(sim, 3)
            })

    return clusters
