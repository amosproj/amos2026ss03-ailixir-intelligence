"""
Image pre-processing pipeline for the Allixer OCR system.

Steps applied (in order):
  1. Load image (JPEG / PNG / PDF page rasterised externally)
  2. Resize so longest side <= MAX_DIMENSION  (keeps VLM token budget in check)
  3. Convert to grayscale
  4. Apply CLAHE (Contrast Limited Adaptive Histogram Equalisation)
  5. Encode back to JPEG base64 for the vision API
"""

from __future__ import annotations
import base64
import io
import cv2
import numpy as np
from PIL import Image


# ── Config ──────────────────────────────────────────────────────────────────
MAX_DIMENSION = 2048   # px — keeps the image large enough for fine text
CLAHE_CLIP_LIMIT = 2.0
CLAHE_TILE_GRID = (8, 8)
OUTPUT_QUALITY = 92    # JPEG quality for the re-encoded image
# ────────────────────────────────────────────────────────────────────────────


def load_image(source: str | bytes) -> np.ndarray:
    """
    Accept a file path (str) or raw bytes and return a BGR numpy array.
    """
    if isinstance(source, (bytes, bytearray)):
        arr = np.frombuffer(source, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    else:
        img = cv2.imread(source, cv2.IMREAD_COLOR)

    if img is None:
        raise ValueError(f"Could not decode image from source: {source!r}")
    return img


def resize_image(img: np.ndarray, max_dim: int = MAX_DIMENSION) -> np.ndarray:
    """Downscale so that the longest side == max_dim, preserving aspect ratio."""
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= max_dim:
        return img
    scale = max_dim / longest
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


def to_grayscale(img: np.ndarray) -> np.ndarray:
    """Convert BGR to single-channel grayscale."""
    if len(img.shape) == 2:
        return img  # already grayscale
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def apply_clahe(gray: np.ndarray) -> np.ndarray:
    """
    Apply CLAHE to enhance local contrast — especially useful for low-quality
    scans, faded ink, or uneven lighting.
    """
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=CLAHE_TILE_GRID)
    return clahe.apply(gray)


def to_base64_jpeg(gray: np.ndarray, quality: int = OUTPUT_QUALITY) -> str:
    """Encode a grayscale numpy array to a base64 JPEG string."""
    # cv2.imencode expects uint8
    success, buf = cv2.imencode(".jpg", gray, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not success:
        raise RuntimeError("cv2.imencode failed")
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def preprocess(
    source: str | bytes,
    *,
    max_dim: int = MAX_DIMENSION,
    grayscale: bool = True,
    clahe: bool = True,
) -> tuple[str, dict]:
    """
    Full pre-processing pipeline.

    Returns
    -------
    base64_jpeg : str
        Ready to embed in a  ``data:image/jpeg;base64,<...>``  URL.
    meta : dict
        Original and processed dimensions for audit logging.
    """
    img = load_image(source)
    original_h, original_w = img.shape[:2]

    img = resize_image(img, max_dim)
    resized_h, resized_w = img.shape[:2]

    if grayscale:
        img = to_grayscale(img)
    if clahe and grayscale:          # CLAHE is only meaningful on grayscale
        img = apply_clahe(img)

    b64 = to_base64_jpeg(img)

    meta = {
        "original_size": (original_w, original_h),
        "processed_size": (resized_w, resized_h),
        "grayscale": grayscale,
        "clahe_applied": clahe and grayscale,
    }
    return b64, meta
