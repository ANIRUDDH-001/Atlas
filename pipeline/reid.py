"""
OSNet x0.25 Re-ID embedding extraction.

Extracts 128-dimensional appearance vectors from person crops for
use by the VisitorGallery re-entry detection system.
"""
import structlog
import numpy as np
import torch
import torchreid  # type: ignore  # type: ignore
import torchvision.transforms as T  # type: ignore
from PIL import Image
from pathlib import Path

logger = structlog.get_logger()

# Input size expected by OSNet
REID_INPUT_HEIGHT = 256
REID_INPUT_WIDTH  = 128

# Preprocessing pipeline matching OSNet training normalization
REID_TRANSFORM = T.Compose([
    T.Resize((REID_INPUT_HEIGHT, REID_INPUT_WIDTH)),
    T.ToTensor(),
    T.Normalize(
        mean=[0.485, 0.456, 0.406],  # ImageNet mean (OSNet trained on)
        std=[0.229, 0.224, 0.225],   # ImageNet std
    ),
])


class ReIDExtractor:
    """
    Extracts appearance embeddings using OSNet x0.25 (MSMT17 pretrained).

    Thread-safety: Not thread-safe. Use one instance per process.
    """

    def __init__(self, model_path: str = "osnet_x0_25_msmt17.pt"):
        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        self.model = self._load_model(model_path)
        self.model.eval()
        logger.info("reid_initialized",
                    model=model_path,
                    device=str(self.device))

    def _load_model(self, model_path: str):
        """
        Load OSNet x0.25 via torchreid.
        Falls back to building from torchreid if weights file not found.
        """
        import torchreid  # type: ignore

        model = torchreid.models.build_model(
            name="osnet_x0_25",
            num_classes=1000,  # Placeholder — we use feature extraction only
            pretrained=True,   # Downloads MSMT17 weights if not cached
        )

        # If a local weights file exists, load it
        weights_path = Path(model_path)
        if weights_path.exists():
            state = torch.load(str(weights_path),
                               map_location=self.device)
            # Handle both raw state dict and wrapped checkpoints
            if "state_dict" in state:
                state = state["state_dict"]
            model.load_state_dict(state, strict=False)
            logger.info("reid_weights_loaded", path=model_path)

        model = model.to(self.device)
        return model

    def extract(self, crop_bgr: np.ndarray) -> np.ndarray | None:
        """
        Extract a normalised appearance embedding from a BGR person crop.

        Args:
            crop_bgr: OpenCV BGR image of the person region

        Returns:
            1-D numpy array of shape (512,), L2-normalised.
            Returns None if crop is invalid (too small, empty).
        """
        if crop_bgr is None or crop_bgr.size == 0:
            return None
        if crop_bgr.shape[0] < 16 or crop_bgr.shape[1] < 8:
            # Crop too small for meaningful embedding
            return None

        # BGR → RGB → PIL
        crop_rgb = crop_bgr[:, :, ::-1].copy()
        pil_img  = Image.fromarray(crop_rgb)

        # Preprocess
        tensor = REID_TRANSFORM(pil_img).unsqueeze(0).to(self.device)

        with torch.no_grad():
            features = self.model(tensor)

        # L2-normalise to unit sphere for cosine similarity comparison
        embedding = features.cpu().numpy().flatten()
        norm = np.linalg.norm(embedding)
        if norm < 1e-8:
            return None
        return embedding / norm

    def batch_extract(
        self,
        crops: list[np.ndarray],
    ) -> list[np.ndarray | None]:
        """
        Extract embeddings for a batch of crops.
        More efficient than calling extract() in a loop for large batches.
        """
        results: list[np.ndarray | None] = []
        valid_indices = []
        valid_tensors = []

        for i, crop in enumerate(crops):
            if crop is None or crop.size == 0:
                results.append(None)
                continue
            if crop.shape[0] < 16 or crop.shape[1] < 8:
                results.append(None)
                continue
            crop_rgb = crop[:, :, ::-1].copy()
            pil_img  = Image.fromarray(crop_rgb)
            valid_tensors.append(REID_TRANSFORM(pil_img))
            valid_indices.append(i)
            results.append(None)  # placeholder

        if not valid_tensors:
            return results

        batch = torch.stack(valid_tensors).to(self.device)
        with torch.no_grad():
            features = self.model(batch)

        embeddings = features.cpu().numpy()
        for j, idx in enumerate(valid_indices):
            emb = embeddings[j]
            norm = np.linalg.norm(emb)
            results[idx] = emb / norm if norm >= 1e-8 else None

        return results


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Compute cosine similarity between two L2-normalised embeddings.
    Since embeddings are already normalised, this is just the dot product.
    Range: -1.0 to 1.0 (retail gallery matches typically > 0.70)
    """
    if a is None or b is None:
        return 0.0
    return float(np.dot(a, b))
