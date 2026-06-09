from django.test import TestCase

from apps.reservations.document_intake_ocr_fixup import (
    fixup_document_ocr_result,
    infer_image_side,
    normalize_document_number,
)
from apps.reservations.document_intake_match import _person_name_keys
from apps.reservations.booking_xls_import import _normalize_guest_name_key


class DocumentIntakeOcrFixupTests(TestCase):
    def test_infer_back_from_pesel_and_mrz(self):
        item = {
            "side": "front",
            "ocr_text": "NUMER PESEL/PERSONAL NUMBER\n83060109166\nORGAN WYDAJACY",
            "mrz_lines": ["IPOLDGN7672550<<<<<<<<<<<<<<<"],
        }
        self.assertEqual(infer_image_side(item), "back")

    def test_fixup_moves_misclassified_front_index_to_back(self):
        ocr = {
            "images": [
                {
                    "index": 0,
                    "side": "front",
                    "ocr_text": "NUMER PESEL/PERSONAL NUMBER",
                    "mrz_lines": ["IPOLDGN7672550<<<<<<<<<<<<<<<"],
                }
            ],
            "persons": [
                {
                    "given_names": "JOANNA",
                    "surnames": "GOLEBIOWSKA",
                    "document_number": "DGN767255",
                    "front_image_index": 0,
                    "back_image_index": None,
                }
            ],
        }
        fixed = fixup_document_ocr_result(ocr)
        person = fixed["persons"][0]
        self.assertIsNone(person["front_image_index"])
        self.assertEqual(person["back_image_index"], 0)
        self.assertEqual(fixed["images"][0]["side"], "back")

    def test_normalize_document_number_strips_spaces(self):
        self.assertEqual(normalize_document_number("DGN 767255"), "DGN767255")

    def test_diacritic_name_keys_match(self):
        person_keys = _person_name_keys(
            {"given_names": "JOANNA JULIA", "surnames": "GOLEBIOWSKA"}
        )
        guest_key = _normalize_guest_name_key("JOANNA JULIA GOŁĘBIOWSKA")
        self.assertIn(guest_key, person_keys)
