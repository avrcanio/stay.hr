"""Face crop from document front photos."""

from __future__ import annotations

import io
from typing import Any

from django.core.files.base import ContentFile
from PIL import Image


def crop_face_jpeg(
    image_path: str,
    bbox: dict[str, Any] | None = None,
) -> ContentFile | None:
    """Crop portrait from document image; bbox is normalized 0-1."""
    try:
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            w, h = im.size
            if bbox and all(k in bbox for k in ("x", "y", "w", "h")):
                x = max(0, int(float(bbox["x"]) * w))
                y = max(0, int(float(bbox["y"]) * h))
                bw = max(1, int(float(bbox["w"]) * w))
                bh = max(1, int(float(bbox["h"]) * h))
            else:
                x = int(0.05 * w)
                y = int(0.12 * h)
                bw = int(0.38 * w)
                bh = int(0.48 * h)

            x2 = min(w, x + bw)
            y2 = min(h, y + bh)
            if x2 <= x or y2 <= y:
                return None

            crop = im.crop((x, y, x2, y2))
            side = min(crop.size)
            if side < 40:
                return None

            buf = io.BytesIO()
            crop.save(buf, format="JPEG", quality=88)
            buf.seek(0)
            return ContentFile(buf.read(), name="face.jpg")
    except Exception:
        return None
