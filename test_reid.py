import numpy as np
from pipeline.reid import ReIDExtractor, cosine_similarity

extractor = ReIDExtractor()

# Create a synthetic 256x128 BGR crop
fake_crop = np.random.randint(0, 255, (256, 128, 3), dtype=np.uint8)
embedding = extractor.extract(fake_crop)

assert embedding is not None, "FAIL: embedding is None"
assert embedding.shape == (512,), f"FAIL: wrong shape {embedding.shape}"
assert abs(np.linalg.norm(embedding) - 1.0) < 1e-5, "FAIL: not normalised"

# Same crop should have cosine similarity 1.0 with itself
sim = cosine_similarity(embedding, embedding)
assert abs(sim - 1.0) < 1e-5, f"FAIL: self-similarity = {sim}"

# Too-small crop returns None
tiny = np.zeros((5, 3, 3), dtype=np.uint8)
result = extractor.extract(tiny)
assert result is None, "FAIL: tiny crop should return None"

print("PASS: All ReID tests passed")
