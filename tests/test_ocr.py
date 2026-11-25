import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError

from ocr import LocalOcr, OcrError, parse_model_response


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

    def test_normalizes_date_dashes_without_filtering_actions(self) -> None:
        records = parse_model_response(
            '{"records":[{"date":"2026-11-12","name":"Anne","action":"frn-?"},'
            '{"date":"17 – x – 26","name":"Lou","action":""},'
            '{"date":"—","name":"Jo","action":"pneu"}]}'
        )
        self.assertEqual([row["date"] for row in records], ["12/11/2026", "17/x/26", ""])
        self.assertEqual([row["action"] for row in records], ["frn-?", "", "pneu"])

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

    def test_explains_how_to_install_missing_model(self) -> None:
        with TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"
            image.write_bytes(b"image")
            error = HTTPError(
                "http://localhost:11434/api/generate",
                404,
                "Not Found",
                {},
                None,
            )
            error.read = lambda: b'{"error":"model not found"}'
            with patch("ocr.urlopen", side_effect=error):
                with self.assertRaisesRegex(OcrError, "ollama pull qwen2.5vl:3b"):
                    LocalOcr().extract(image)

    def test_explains_incomplete_ollama_response(self) -> None:
        with TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"
            image.write_bytes(b"image")
            response = json.dumps(
                {"model": "", "response": "", "done": False}
            ).encode()
            mocked_response = unittest.mock.MagicMock()
            mocked_response.__enter__.return_value.read.return_value = response
            with patch("ocr.urlopen", return_value=mocked_response):
                with self.assertRaisesRegex(OcrError, "photo nette"):
                    LocalOcr().extract(image)


if __name__ == "__main__":
    unittest.main()
