"""Compare local OCR on the sample photograph and on manually cropped bands."""

from __future__ import annotations

import argparse
import csv
import unicodedata
from bisect import bisect_right
from difflib import SequenceMatcher
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw, ImageFont

from action_keywords import find_components
from ocr import LocalOcr, OcrError

ROOT = Path(__file__).resolve().parent
PHOTO = ROOT / "photo_2026-11-24_21-41-07.jpg"
FIELDS = ("date", "name", "action")
# Each rectangle includes all three columns and ends between interventions.
BANDS = (
    (27, 122, 818, 307),
    (26, 307, 832, 535),
    (25, 535, 843, 758),
    (24, 758, 849, 1016),
    (22, 1016, 855, 1178),
)
EXPECTED_PER_BAND = (5, 4, 5, 4, 3)
# Hand-marked row separators, in original image coordinates, for each column.
# The first band's handwriting slopes across the page.
ROW_SEPARATORS = (
    ((181, 216, 248, 278), (172, 206, 236, 265), (155, 185, 223, 254)),
    ((388, 435, 468), (388, 435, 468), (378, 428, 463)),
    ((566, 600, 633, 682), (566, 600, 633, 682), (566, 600, 632, 682)),
    ((852, 914, 958), (852, 914, 958), (852, 914, 965)),
    ((1073, 1135), (1073, 1136), (1090, 1145)),
)

# Each cell specifies left, right, and the top and bottom edges at both sides.
# The fourth name extends past the printed separator near x=402.
FOCUSED_CELLS = (
    ((174, 405, 139, 128, 180, 166), (408, 806, 119, 104, 151, 146)),
    ((174, 400, 180, 166, 211, 200), (404, 802, 151, 146, 183, 184)),
    ((174, 404, 214, 199, 247, 225), (407, 811, 183, 186, 227, 231)),
    ((174, 445, 243, 224, 274, 253), (445, 810, 219, 218, 254, 256)),
    ((173, 406, 271, 253, 306, 294), (405, 812, 250, 248, 296, 290)),
)

FOCUSED_PROMPT = (
    "Cette image représente une seule intervention d'un registre manuscrit français. "
    "En haut figure le nom et prénom, au milieu l'action. "
    "L'image du bas montre la même ligne pour le contexte. "
    "Transcris le nom complet dans name et uniquement l'action dans action, lettre par lettre. "
    "Conserve les abréviations et la ponctuation, sans reformuler ni deviner. "
    "Laisse date vide. Réponds uniquement avec un objet JSON de cette forme : "
    '{"records":[{"date":"","name":"","action":""}]}'
)


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def compare(expected: list[tuple], actual: list[tuple]) -> None:
    expected = [tuple(map(normalize, row)) for row in expected]
    actual = [tuple(map(normalize, row)) for row in actual]
    # Align by approximate name in reading order. Repeated dates are weak identifiers.
    scores = {(0, 0): (0.0, [])}
    for i in range(len(expected) + 1):
        for j in range(len(actual) + 1):
            if not (i or j):
                continue
            options = []
            if i:
                options.append(scores[i - 1, j])
            if j:
                options.append(scores[i, j - 1])
            if i and j and expected[i - 1][1] and actual[j - 1][1]:
                similarity = SequenceMatcher(None, expected[i - 1][1], actual[j - 1][1]).ratio()
                if similarity >= 0.55:
                    score, matches = scores[i - 1, j - 1]
                    options.append((score + similarity, [*matches, (i - 1, j - 1)]))
            scores[i, j] = max(options, key=lambda item: item[0])

    _, matches = scores[len(expected), len(actual)]
    print(f"  Entrées alignées par nom : {len(matches)}/{len(expected)}")
    print(f"  Entrées attendues non alignées : {len(expected) - len(matches)}")
    print(f"  Entrées OCR non alignées : {len(actual) - len(matches)}")
    for column, field in enumerate(("Dates", "Noms", "Actions")):
        correct = sum(expected[i][column] == actual[j][column] for i, j in matches)
        filled = sum(bool(row[column]) for row in actual)
        print(f"  {field} : {correct}/{len(expected)} exacts, {filled}/{len(actual)} renseignés")


def extract(ocr: LocalOcr, image: Path, label: str) -> list[tuple]:
    try:
        rows = ocr.extract(image)
    except OcrError as error:
        print(f"{label} : {error}", flush=True)
        return []
    print(f"{label} : {len(rows)} entrées", flush=True)
    return [tuple(row[field] for field in FIELDS) for row in rows]


def extract_paddle() -> list[tuple]:
    from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

    engine = RapidOCR(params={
        "Rec.lang_type": LangRec.LATIN,
        "Rec.ocr_version": OCRVersion.PPOCRV5,
        "Rec.model_type": ModelType.MOBILE,
        "Global.use_cls": False,
        "EngineConfig.onnxruntime.intra_op_num_threads": 4,
    })
    rows = []
    with Image.open(PHOTO) as photo:
        for bounds, separators, count in zip(BANDS, ROW_SEPARATORS, EXPECTED_PER_BAND):
            left, top, _, _ = bounds
            result = engine(photo.crop(bounds), text_score=0.25)
            cells = [[[] for _ in FIELDS] for _ in range(count)]
            if result.boxes is not None:
                for box, value in zip(result.boxes, result.txts):
                    x, y = box.mean(axis=0)
                    column = bisect_right((177, 402), x + left)
                    row = bisect_right(separators[column], y + top)
                    cells[row][column].append((float(y), float(x), value.strip()))
            for row in cells:
                fields = tuple(
                    " ".join(value for _, _, value in sorted(fragments, key=lambda item: (
                        round(item[0] / 15), item[1],
                    )))
                    for fragments in row
                )
                if any(fields):
                    rows.append(fields)
    return rows


def crop_cell(photo: Image.Image, bounds: tuple[int, ...]) -> Image.Image:
    left, right, top_left, top_right, bottom_left, bottom_right = bounds
    height = max(bottom_left - top_left, bottom_right - top_right)
    return photo.transform(
        ((right - left) * 2, height * 2),
        Image.Transform.QUAD,
        (left, top_left, left, bottom_left, right, bottom_right, right, top_right),
        resample=Image.Resampling.BICUBIC,
    )


def edit_distance(reference: str, prediction: str) -> int:
    previous = list(range(len(prediction) + 1))
    for i, expected_char in enumerate(reference, start=1):
        current = [i]
        for j, actual_char in enumerate(prediction, start=1):
            current.append(min(
                current[-1] + 1, previous[j] + 1,
                previous[j - 1] + (expected_char != actual_char),
            ))
        previous = current
    return previous[-1]


def compare_focused(expected: list[tuple], rows: list[tuple]) -> None:
    if len(rows) != len(expected):
        print(f"  Comparaison positionnelle impossible ({len(rows)} lignes pour {len(expected)}).")
        return
    for column, label in ((1, "Noms"), (2, "Actions")):
        cells = [(normalize(a[column]), normalize(b[column])) for a, b in zip(expected, rows)]
        exact = sum(reference == prediction for reference, prediction in cells)
        errors = [edit_distance(reference, prediction) for reference, prediction in cells]
        total = sum(len(reference) for reference, _ in cells)
        print(f"  {label} : {exact}/{len(cells)} exacts, {sum(errors)}/{total} écarts de caractères")
        print("    Écarts par ligne :", ", ".join(map(str, errors)))
    compare_components(expected, rows)


def compare_components(expected: list[tuple], rows: list[tuple]) -> None:
    cells = [(find_components(a[2]), find_components(b[2])) for a, b in zip(expected, rows)]
    correct = sum(len(reference & prediction) for reference, prediction in cells)
    total = sum(len(reference) for reference, _ in cells)
    added = sum(len(prediction - reference) for reference, prediction in cells)
    exact = sum(reference == prediction for reference, prediction in cells)
    print(f"  Composants : {correct}/{total} retrouvés, {added} ajoutés, {exact}/{len(cells)} lignes exactes")


def run_focused(ocr: LocalOcr, expected: list[tuple]) -> None:
    with TemporaryDirectory() as directory, Image.open(PHOTO) as photo:
        path = Path(directory) / "extrait.png"
        photo.crop(BANDS[0]).save(path)
        compare_focused(expected, extract(ocr, path, "Bande entière"))
        rows = []
        font = ImageFont.load_default(size=20)
        for index, (name, action) in enumerate(FOCUSED_CELLS, start=1):
            context = photo.crop((27, min(name[2], action[3]), 818, max(name[4], action[5])))
            panels = (
                ("Nom", crop_cell(photo, name)),
                ("Action", crop_cell(photo, action)),
                ("Contexte", context),
            )
            width = max(panel.width for _, panel in panels)
            height = sum(panel.height + 36 for _, panel in panels)
            image = Image.new("RGB", (width + 24, height + 12), "white")
            draw = ImageDraw.Draw(image)
            top = 8
            for label, panel in panels:
                draw.text((12, top), label, font=font, fill="black")
                image.paste(panel, (12, top + 28))
                top += panel.height + 36
            image.save(path)
            try:
                result = ocr.extract(path, prompt=FOCUSED_PROMPT)
                if len(result) != 1:
                    raise OcrError(f"{len(result)} entrées renvoyées, une attendue")
            except OcrError as error:
                print(f"  Ligne {index} : {error}", flush=True)
                rows.append(("", "", ""))
            else:
                rows.append(tuple(result[0][field] for field in FIELDS))
                print(f"  Ligne {index} traitée", flush=True)
    print("Recadrages ciblés")
    compare_focused(expected, rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--bandes-seules", action="store_true")
    mode.add_argument("--paddle", action="store_true", help="tester PaddleOCR sur les bandes")
    mode.add_argument("--cible", action="store_true", help="relire les cinq premières interventions")
    args = parser.parse_args()
    with (ROOT / "expected_result.csv").open(encoding="utf-8", newline="") as source:
        reader = csv.reader(source, strict=True)
        next(reader)
        expected = [tuple(row) for row in reader if row]
    if len(expected) != sum(EXPECTED_PER_BAND) or any(len(row) != 3 for row in expected):
        raise ValueError("La référence doit contenir les 21 entrées à trois colonnes.")
    if args.paddle:
        print("PaddleOCR sur les bandes, avec séparateurs de lignes manuels", flush=True)
        compare(expected, extract_paddle())
        return
    ocr = LocalOcr()
    if args.cible:
        run_focused(ocr, expected[:len(FOCUSED_CELLS)])
        return
    if not args.bandes_seules:
        compare(expected, extract(ocr, PHOTO, "Page entière"))
    rows = []
    with TemporaryDirectory() as directory, Image.open(PHOTO) as photo:
        for index, (bounds, count) in enumerate(zip(BANDS, EXPECTED_PER_BAND), start=1):
            path = Path(directory) / f"bande-{index}.png"
            photo.crop(bounds).save(path)
            rows.extend(extract(ocr, path, f"Bande {index} ({count} attendues)"))
    print("Bandes réunies", flush=True)
    compare(expected, rows)


if __name__ == "__main__":
    main()
