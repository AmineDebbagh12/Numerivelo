from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MODEL_NAME = "qwen2.5vl:3b"
OLLAMA_URL = "http://localhost:11434/api/generate"


class OcrError(Exception):
    """An expected problem while communicating with the local OCR model."""


def normalize_date(value: str) -> str:
    value = value.strip()
    dash = r"[-‐‑–—−]"
    if re.fullmatch(rf"(?:{dash}\s*)+", value):
        return ""
    iso = re.fullmatch(rf"(\d{{4}})\s*{dash}\s*(\d{{1,2}})\s*{dash}\s*(\d{{1,2}})", value)
    if iso:
        year, month, day = iso.groups()
        return f"{day}/{month}/{year}"
    return re.sub(rf"(?<=[0-9xX?])\s*{dash}\s*(?=[0-9xX?])", "/", value)


def parse_model_response(response: str) -> list[dict[str, str]]:
    response = response.strip()
    if response.startswith(("```json\n", "```\n")) and response.endswith("```"):
        response = response.split("\n", 1)[1][:-3]
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
        values[0] = normalize_date(values[0])
        records.append(dict(zip(("date", "name", "action"), values)))
    return records


class LocalOcr:
    def __init__(self, model: str = MODEL_NAME, endpoint: str = OLLAMA_URL) -> None:
        self.model = model
        self.endpoint = endpoint

    def extract(self, image_path: Path, *, prompt: str | None = None) -> list[dict[str, str]]:
        try:
            encoded_image = base64.b64encode(image_path.read_bytes()).decode("ascii")
        except OSError as exc:
            raise OcrError(f"Impossible de lire l'image : {exc}") from exc

        prompt = prompt or (
            "Lis cette photo d'un registre manuscrit en français. "
            "Extrais toutes les lignes visibles du tableau principal dans l'ordre. "
            "Les en-têtes « Quand ? », « Qui ? » et « Quoi ? » correspondent "
            "respectivement à la date, au nom et prénom, et à l'action. "
            "Une intervention peut occuper plusieurs lignes manuscrites : rattache "
            "la suite du texte à la même action. "
            "Ignore les en-têtes, les numéros de page et les fragments d'une page voisine. "
            "Dans l'action, transcris aussi les fragments lisibles, même s'il ne reste "
            "qu'un mot ou une abréviation. Conserve particulièrement les noms des pièces "
            "de vélo que tu arrives à lire, même si la phrase est incomplète. "
            "Laisse une action vide uniquement si elle est absente ou si aucun fragment "
            "n'est lisible. Laisse aussi vides les dates et les noms absents ou illisibles. "
            "N'invente rien et conserve le texte visible tel qu'il est écrit. "
            'Réponds uniquement en JSON, au format '
            '{"records":[{"date":"", "name":"", "action":""}]}.'
        )
        request_body = {
            "model": self.model,
            "prompt": prompt,
            "images": [encoded_image],
            "stream": False,
            # The installed GPU runner failed to generate text for the sample image.
            "options": {
                "temperature": 0.2,
                "seed": 42,
                "num_ctx": 8192,
                "repeat_penalty": 1.1,
                "num_gpu": 0,
            },
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
        except HTTPError as exc:
            try:
                details = json.loads(exc.read().decode("utf-8")).get("error", "")
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                details = ""
            if "model" in details.lower() and "not found" in details.lower():
                raise OcrError(
                    f"Le modèle OCR « {self.model} » n'est pas installé. "
                    f"Dans un terminal, exécutez : ollama pull {self.model}"
                ) from exc
            message = f"Erreur Ollama (HTTP {exc.code})"
            if details:
                message += f" : {details}"
            raise OcrError(message) from exc
        except URLError as exc:
            raise OcrError(
                f"Impossible de joindre Ollama à {self.endpoint}. "
                "Vérifiez qu'Ollama est démarré et réessayez."
            ) from exc
        except TimeoutError as exc:
            raise OcrError("Le traitement a dépassé le délai d'attente.") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OcrError("Ollama a renvoyé une réponse illisible.") from exc

        if not isinstance(result, dict) or not isinstance(result.get("response"), str):
            raise OcrError("La réponse d'Ollama ne contient pas le résultat OCR attendu.")
        response_text = result["response"].strip()
        if not response_text or result.get("done") is False:
            raise OcrError(
                "Ollama n'a pas terminé la reconnaissance et n'a renvoyé aucun texte. "
                "Le modèle local peut être en difficulté avec cette écriture ou cette photo. "
                "Essayez une photo nette, cadrée sur une seule page, puis relancez le traitement."
            )
        return parse_model_response(response_text)
