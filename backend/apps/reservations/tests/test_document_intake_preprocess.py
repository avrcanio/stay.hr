from django.test import TestCase

from apps.reservations.document_intake_preprocess import (
    dedupe_image_bytes,
    remap_ocr_indices_to_original,
)


class DocumentIntakePreprocessTests(TestCase):
    def test_dedupe_11_to_6_unique(self):
        unique_a = b"image-a-front"
        unique_b = b"image-b-back"
        unique_c = b"contract-page"
        unique_d = b"adac-card"
        unique_e = b"image-e-front"
        unique_f = b"image-f-back"
        # 11 bytes with 5 duplicates (mirrors #22 pattern)
        batch = [
            unique_a,
            unique_b,
            unique_c,
            unique_d,
            unique_a,
            unique_b,
            unique_d,
            unique_e,
            unique_f,
            unique_e,
            unique_f,
        ]
        unique, mapping, dropped = dedupe_image_bytes(batch)
        self.assertEqual(len(unique), 6)
        self.assertEqual(len(dropped), 5)
        self.assertEqual(set(dropped), {4, 5, 6, 9, 10})
        self.assertEqual(mapping, [0, 1, 2, 3, 7, 8])

    def test_remap_ocr_indices_to_original(self):
        ocr_result = {
            "images": [{"index": 0, "side": "front"}, {"index": 1, "side": "back"}],
            "persons": [{"front_image_index": 0, "back_image_index": 1}],
        }
        remapped = remap_ocr_indices_to_original(ocr_result, [0, 1, 7, 8])
        self.assertEqual(remapped["images"][0]["index"], 0)
        self.assertEqual(remapped["images"][1]["index"], 1)
        self.assertEqual(remapped["persons"][0]["front_image_index"], 0)
        self.assertEqual(remapped["persons"][0]["back_image_index"], 1)
