"""
inputs/lingoqa.py

LingoQA video-QA dataset loader.
Returns a list of sample dicts + an open ZipFile for frame loading.

Input key: "lingoqa"
Used by: models/cosmos_reason2b

Forward-only: this package imports only from lib/. It does not import
from runtimes/, benchmark/, results/, or site/.
"""

import io
import math
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image as PILImage  # type: ignore[import]

VAL_PARQUET = Path("/workspace/data/lingoqa/evaluation/val.parquet")
IMAGES_ZIP  = Path("/workspace/data/lingoqa/evaluation/evaluation/images.zip")
MAX_FRAMES  = 8
MAX_PIXELS  = 196_608   # 512×384 — matches Alpamayo 1.5 eval protocol
MIN_PIXELS  = 163_840


def load(unused_image_path: Path = VAL_PARQUET) -> tuple[list[dict], zipfile.ZipFile]:
    """
    Load LingoQA eval split.

    Returns (samples, zf) where samples is a list of 500 dicts:
        {question_id, question, answers: [str, str], frame_paths: [str, ...]}
    and zf is an open ZipFile for reading frames.

    The unused_image_path argument exists to satisfy the runner interface
    (input_module.load(model_spec.sample_image_path())) — it is ignored.
    """
    import pyarrow.parquet as pq  # type: ignore[import]

    table = pq.read_table(VAL_PARQUET)
    grouped: dict[str, dict[str, Any]] = {}
    for i in range(table.num_rows):
        qid = table["question_id"][i].as_py()
        if qid not in grouped:
            grouped[qid] = {
                "question_id": qid,
                "question": table["question"][i].as_py(),
                "frame_paths": table["images"][i].as_py(),
                "answers": [],
            }
        grouped[qid]["answers"].append(table["answer"][i].as_py())

    zf = zipfile.ZipFile(IMAGES_ZIP, "r")
    return list(grouped.values()), zf


def resize_frame(img: PILImage.Image) -> PILImage.Image:
    """Resize to MAX_PIXELS budget, 32-px aligned — matches Alpamayo 1.5."""
    w, h = img.size
    scale = min(1.0, math.sqrt(MAX_PIXELS / (w * h)))
    new_w = max(32, int(w * scale) // 32 * 32)
    new_h = max(32, int(h * scale) // 32 * 32)
    if (new_w, new_h) == (w, h):
        return img
    return img.resize((new_w, new_h), PILImage.LANCZOS)


def load_frames(zf: zipfile.ZipFile, frame_paths: list[str]) -> list[PILImage.Image]:
    """Evenly sample up to MAX_FRAMES frames from a clip, resized to MAX_PIXELS."""
    paths = frame_paths
    if len(paths) > MAX_FRAMES:
        step = len(paths) / MAX_FRAMES
        paths = [paths[int(i * step)] for i in range(MAX_FRAMES)]
    frames = []
    for p in paths:
        try:
            data = zf.read(p)
            frames.append(resize_frame(PILImage.open(io.BytesIO(data)).convert("RGB")))
        except Exception:  # noqa: BLE001
            pass
    return frames
