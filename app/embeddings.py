from openai import OpenAI
import numpy as np

def generate_embeddings(pages):
    if not pages:
        return []

    client = OpenAI()
    texts = [p["content"][:2000] for p in pages]

    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts
    )

    return [np.array(e.embedding) for e in response.data]
