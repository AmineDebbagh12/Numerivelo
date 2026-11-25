# Registre manuscrit

Application de bureau gratuite pour transcrire des photos de registres manuscrits, visualiser les interventions et exporter le tableau vers Excel. Le traitement OCR s'effectue sur l'ordinateur avec Ollama et le modèle vision `qwen2.5vl:3b`.

La reconnaissance d'écriture manuscrite peut faire des erreurs, en particulier sur les photos inclinées ou floues. Le programme permet de corriger les trois colonnes (date, nom / prénom, action).

## Installation

Prérequis : Python 3.10 ou plus récent avec Tkinter, et [Ollama](https://ollama.com/) installé. Sous Debian ou Ubuntu, installez les outils Python manquants si nécessaire avec `sudo apt install python3-tk python3-pip python3-venv`.

1. Dans un terminal, téléchargez le modèle une fois :

   ```sh
   ollama pull qwen2.5vl:3b
   ```

2. Depuis le dossier du projet, créez un environnement virtuel et installez les dépendances dedans :

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   ```

3. Lancez Ollama. Si le service ne tourne pas déjà, ouvrez un terminal et exécutez :

   ```sh
   ollama serve
   ```

   Si vous voyez `bind: address already in use`, Ollama est probablement déjà lancé : ne relancez pas cette commande et passez à l'étape suivante.

4. Dans le terminal où l'environnement virtuel est activé, lancez le programme :

   ```sh
   python app.py
   ```

À chaque nouvelle ouverture du terminal, réactivez l'environnement avant de lancer le programme avec `source .venv/bin/activate`.

Le modèle est téléchargé uniquement à l'étape 1. Après cela, le logiciel traite les images localement, sans connexion à un service OCR distant. Le traitement utilise le processeur et peut prendre du temps selon l'ordinateur.

## Utilisation

1. Choisissez le dossier contenant les images (`.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, `.bmp` ou `.webp`).
2. Cliquez sur **Lire les images** et attendez la fin du traitement.
3. Vérifiez chaque ligne. Double-cliquez sur une cellule pour la corriger ; vous pouvez aussi ajouter ou supprimer des lignes.
4. Cliquez sur **Visualiser les données…** et choisissez la date, le nom / prénom, l'action ou les **Composants vélo**. Chaque ouverture utilise les valeurs actuelles du tableau. Le graphique par action regroupe les libellés complets en ignorant les différences de casse et d'espacement. Le graphique par composant utilise un lexique local et compte chaque composant une fois par intervention. Une intervention peut apparaître dans plusieurs barres. Les dates françaises reconnues avec une année sur deux chiffres sont interprétées entre 2000 et 2099.
5. Cliquez sur **Exporter vers Excel…** pour enregistrer un classeur `.xlsx` avec les colonnes Date, Nom / prénom et Action.

## Tests

```sh
python3 -m unittest discover -s tests
```

## Comparatif OCR sur la photo exemple

Le script utilise les 21 interventions de `expected_result.csv` et les cinq bandes
découpées manuellement dans la photo exemple. Il aligne les lignes par similarité
du nom dans l'ordre du registre, puis compare les champs en ignorant la casse et
les écarts d'espacement.

```sh
python -m pip install Pillow
python benchmark_ocr.py
```

Pour l'essai PaddleOCR, le script réutilise les mêmes bandes et attribue les
fragments détectés aux cellules à partir de séparateurs marqués manuellement.
RapidOCR télécharge les poids publics nécessaires au premier lancement.

```sh
python -m pip install rapidocr==3.10.0 onnxruntime
python benchmark_ocr.py --paddle
```

Pour comparer les cinq premières interventions à des recadrages adaptés à
chaque ligne, lancez `python benchmark_ocr.py --cible`. Qwen reçoit le nom et
l'action agrandis, avec la ligne entière pour le contexte. Le script compte
les cellules exactes et les insertions, suppressions et substitutions de
caractères, hors casse et écarts d'espacement. Il compare aussi les composants
retrouvés avec le même lexique sur le CSV de référence et sur les actions OCR.
