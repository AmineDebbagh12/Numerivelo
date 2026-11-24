# Registre manuscrit vers Excel

Petit programme de bureau gratuit qui lit des photos de registres manuscrits et exporte les résultats vers Excel. Le traitement OCR s'effectue sur l'ordinateur avec Ollama et le modèle vision `qwen2.5vl:3b` ; les images ne sont pas envoyées à un service en ligne.

La reconnaissance d'écriture manuscrite peut faire des erreurs, en particulier sur les photos inclinées ou floues. Le programme permet de corriger les trois colonnes (date, nom, action) avant l'export.

## Installation

Prérequis : Python 3.10 ou plus récent avec Tkinter, et [Ollama](https://ollama.com/) installé. Sous Debian ou Ubuntu, installez les outils Python manquants si nécessaire avec `sudo apt install python3-tk python3-pip`.

1. Dans un terminal, téléchargez le modèle une fois :

   ```sh
   ollama pull qwen2.5vl:3b
   ```

2. Installez la dépendance Python :

   ```sh
   python3 -m pip install -r requirements.txt
   ```

3. Lancez Ollama. Si le service ne tourne pas déjà, ouvrez un terminal et exécutez :

   ```sh
   ollama serve
   ```

4. Dans un autre terminal, depuis ce dossier, lancez le programme :

   ```sh
   python3 app.py
   ```

Le modèle est téléchargé uniquement à l'étape 1. Après cela, le logiciel traite les images localement, sans connexion à un service OCR distant. Le premier traitement peut être lent selon l'ordinateur.

## Utilisation

1. Choisissez le dossier contenant les images (`.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, `.bmp` ou `.webp`).
2. Cliquez sur **Lire les images** et attendez la fin du traitement.
3. Vérifiez chaque ligne. Double-cliquez sur une cellule pour la corriger ; vous pouvez aussi ajouter ou supprimer des lignes.
4. Cliquez sur **Exporter vers Excel…** pour enregistrer un classeur `.xlsx` avec les colonnes Date, Nom et Action.

## Tests

```sh
python3 -m unittest discover -s tests
```
