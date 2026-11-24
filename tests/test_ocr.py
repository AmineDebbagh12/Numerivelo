import unittest

from ocr import OcrError, parse_model_response


class ParseModelResponseTests(unittest.TestCase):
    def test_parses_records_in_column_order(self) -> None:
        records = parse_model_response(
            '{"records":[{"date":"12/11/26","name":"Anne","action":"Réglage"}]}'
        )
        self.assertEqual(
            records,
            [{"date": "12/11/26", "name": "Anne", "action": "Réglage"}],
        )

    def test_accepts_no_detected_rows(self) -> None:
        self.assertEqual(parse_model_response('{"records":[]}'), [])

    def test_rejects_missing_records(self) -> None:
        with self.assertRaises(OcrError):
            parse_model_response("{}")

    def test_rejects_non_text_fields(self) -> None:
        with self.assertRaises(OcrError):
            parse_model_response(
                '{"records":[{"date":12,"name":"Anne","action":"Réglage"}]}'
            )

    def test_rejects_invalid_json(self) -> None:
        with self.assertRaises(OcrError):
            parse_model_response("not json")


if __name__ == "__main__":
    unittest.main()
