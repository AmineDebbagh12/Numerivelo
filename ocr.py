from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


MODEL_NAME = "qwen2.5vl:3b"
OLLAMA_URL = "http://localhost:11434/api/generate"

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "records": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "name": {"type": "string"},
                    "action": {"type": "string"},
                },
                "required": ["date", "name", "action"],
            },
        }
    },
    "required": ["records"],
}


class OcrError(Exception):
    """An expected problem while communicating with the local OCR model."""


def parse_model_response(response: str) -> list[dict[str, str]]:
    try:
        payload: Any = json.loads(response)
    except json.JSONDecodeError as exc:
        raise OcrError("Le modèle a renvoyé une réponse qui n'est pas du JSON valide.") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise OcrError("La réponse du modèle ne contient pas la liste « records » attendue.")

    records: list[dict[str, str]] = []
    for index, record in enumerate(payload["records"], start=1):
        if not isinstance(record, dict):
            raise OcrError(f"La ligne {index} renvoyée par le modèle est invalide.")
        values = [record.get(field) for field in ("date", "name", "action")]
        if not all(isinstance(value, str) for value in values):
            raise OcrError(f"La ligne {index} ne contient pas trois champs texte valides.")
        records.append(dict(zip(("date", "name", "action"), values)))
    return records


class LocalOcr:
    def __init__(self, model: str = MODEL_NAME, endpoint: str = OLLAMA_URL) -> None:
        self.model = model
        self.endpoint = endpoint

    def extract(self, image_path: Path) -> list[dict[str, str]]:
        try:
            encoded_image = base64.b64encode(image_path.read_bytes()).decode("ascii")
        except OSError as exc:
            raise OcrError(f"Impossible de lire l'image : {exc}") from exc

        prompt = (
            "Lis cette photo d'un registre manuscrit en français. "
            "Extrais toutes les lignes visibles du tableau principal dans l'ordre. "
            "Le tableau comporte les colonnes date, nom et action. "
            "Ignore les titres de colonnes et le texte d'une page voisine si elle apparaît. "
            "N'invente jamais une information : si un champ est illisible ou absent, "
            "renvoie une chaîne vide pour ce champ. Conserve le texte tel qu'il est écrit."
        )
        request_body = {
            "model": self.model,
            "prompt": prompt,
            "images": [encoded_image],
            "stream": False,
            "format": _RESPONSE_SCHEMA,
            "options": {"temperature": 0},
        }
        request = Request(
            self.endpoint,
            data=json.dumps(request_body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=600) as response:
                result: Any = json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            raise OcrError(
                "Impossible de joindre Ollama en local. Vérifiez qu'Ollama est installé "
                "et démarré, puis réessayez."
            ) from exc
        except TimeoutError as exc:
            raise OcrError("Le traitement a dépassé le délai d'attente.") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OcrError("Ollama a renvoyé une réponse illisible.") from exc

        if not isinstance(result, dict) or not isinstance(result.get("response"), str):
            raise OcrError("La réponse d'Ollama ne contient pas le résultat OCR attendu.")
        return parse_model_response(result["response"])
