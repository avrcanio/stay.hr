from unittest.mock import patch

from django.test import TestCase

from apps.ai.document_ocr import merge_persons, run_orphan_document_ocr


class DocumentOcrOrphanTests(TestCase):
    @patch("apps.ai.document_ocr.complete_vision_json")
    def test_orphan_pass_returns_persons_from_subset(self, mock_complete):
        mock_complete.return_value = {
            "images": [{"index": 0, "side": "front"}, {"index": 1, "side": "back"}],
            "persons": [
                {
                    "given_names": "Frank",
                    "surnames": "Thiele",
                    "document_number": "L3G9RM1TK",
                    "document_type": "national_id",
                    "front_image_index": 0,
                    "back_image_index": 1,
                },
            ],
        }
        bytes_list = [b"a", b"b", b"c", b"d", b"e", b"f", b"g", b"h"]
        result = run_orphan_document_ocr(
            image_bytes_list=bytes_list,
            orphan_indices=[6, 7],
        )
        self.assertEqual(len(result["persons"]), 1)
        self.assertEqual(result["persons"][0]["surnames"], "Thiele")
        self.assertEqual(result["persons"][0]["front_image_index"], 6)
        self.assertEqual(result["persons"][0]["back_image_index"], 7)

    def test_merge_persons_dedupes_by_document_number(self):
        existing = [
            {
                "given_names": "Gabriele",
                "surnames": "Boettcher",
                "document_number": "L3H8V4JW1",
                "front_image_index": 0,
                "back_image_index": 1,
            },
        ]
        extra = [
            {
                "given_names": "Gabriele",
                "surnames": "Boettcher",
                "document_number": "L3H8V4JW1",
                "front_image_index": 4,
                "back_image_index": 5,
            },
            {
                "given_names": "Frank",
                "surnames": "Thiele",
                "document_number": "L3G9RM1TK",
                "front_image_index": 7,
                "back_image_index": 8,
            },
        ]
        merged = merge_persons(existing, extra)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[1]["surnames"], "Thiele")
