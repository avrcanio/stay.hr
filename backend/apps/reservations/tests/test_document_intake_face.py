from io import BytesIO
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from PIL import Image

from apps.reservations.document_intake_face import (
    _is_placeholder_llm_bbox,
    _select_best_face,
    crop_face_jpeg,
)


class FaceCropHeuristicsTests(SimpleTestCase):
    def test_rejects_prompt_placeholder_bbox(self):
        self.assertTrue(_is_placeholder_llm_bbox({"x": 0.1, "y": 0.15, "w": 0.25, "h": 0.35}))
        self.assertFalse(_is_placeholder_llm_bbox({"x": 0.18, "y": 0.34, "w": 0.22, "h": 0.22}))

    def test_select_best_face_prefers_left_portrait(self):
        w, h = 1200, 1600
        faces = [
            (358, 134, 744, 744),  # false positive — too large
            (250, 613, 257, 257),  # real portrait
        ]
        best = _select_best_face(faces, image_w=w, image_h=h)
        self.assertEqual(best, (250, 613, 257, 257))

    def test_select_best_face_polish_id_false_positive(self):
        """Small mid-card false positive vs large left portrait (guest #2262 case)."""
        w, h = 1600, 1130
        faces = [
            (488, 454, 104, 104),  # guilloche / hologram
            (189, 528, 341, 341),  # real portrait
        ]
        best = _select_best_face(faces, image_w=w, image_h=h)
        self.assertEqual(best, (189, 528, 341, 341))

    def test_rejects_list_placeholder_bbox(self):
        self.assertTrue(_is_placeholder_llm_bbox([0.1, 0.2, 0.3, 0.4]))


@override_settings(MEDIA_ROOT="/tmp/stay_test_face_media")
class FaceCropIntegrationTests(SimpleTestCase):
    def test_crop_face_jpeg_uses_opencv_when_available(self):
        buf = BytesIO()
        Image.new("RGB", (120, 120), color=(200, 180, 160)).save(buf, format="JPEG")
        path = "/tmp/stay_test_face_sample.jpg"
        with open(path, "wb") as fh:
            fh.write(buf.getvalue())

        with patch(
            "apps.reservations.document_intake_face.detect_face_bbox_pixels",
            return_value=(10, 15, 40, 40),
        ):
            result = crop_face_jpeg(path, {"x": 0.1, "y": 0.15, "w": 0.25, "h": 0.35})

        self.assertIsNotNone(result)
        img = Image.open(BytesIO(result.read()))
        self.assertEqual(img.size, (256, 256))
