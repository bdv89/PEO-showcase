# Installer / mettre à jour

Deux façons d'utiliser l'oscilloscope PEO sous Windows :

| Usage | Lancement | Prérequis |
|-------|-----------|-----------|
| **Dossier autonome** (poste de manip) | double-clic `Oscilloscope\Oscilloscope.bat` | aucun : Python 3.12 et dépendances embarqués |
| **Depuis les sources** (développement) | `.\.venv\Scripts\python.exe launcher.py` | Python 3.12 |

Le script **`install.ps1`** installe et met à jour les deux. Il est **relançable sans
risque** : chaque étape ne fait que ce qui manque. Un second passage prend quelques secondes
et ne change rien.

## Nouvelle machine (depuis GitHub)

Une seule ligne, à coller dans un terminal PowerShell. Elle :
- installe Git et Python 3.12 s'ils manquent ;
- recharge le PATH ;
- clone le dépôt dans `%USERPROFILE%\PEO-showcase` ;
- lance `install.ps1`.

```powershell
winget install -e --id Git.Git; winget install -e --id Python.Python.3.12; $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User'); git clone https://github.com/bdv89/PEO-showcase.git "$HOME\PEO-showcase"; cd "$HOME\PEO-showcase"; powershell -ExecutionPolicy Bypass -File .\install.ps1
```

- Dépôt public : aucun compte GitHub n'est nécessaire.
- Si Git ou Python sont déjà installés, winget le signale et la ligne continue.
- **Dossier autonome** (poste de manip, sans Python) : télécharger
  `PEOscillo-windows-vX.Y.Z.zip` depuis https://github.com/bdv89/PEOscillo/releases,
  dézipper, puis double-cliquer `Oscilloscope.bat`.

## Mettre à jour

```powershell
cd "$HOME\PEO-showcase"
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

## Ce que fait `install.ps1`

1. **Code** : `git pull` si le dossier est un dépôt git. En cas de modifications locales, il
   s'arrête sans rien écraser.
2. **`.venv`** en **Python 3.12** :
   - créé s'il manque ;
   - **recréé s'il est dans une autre version**, par exemple 3.15 alpha, où `h5py` ne
     s'installe pas ;
   - `-Recreer` force la recréation.
3. **Dépendances** (`requirements.txt`) : pip n'installe que ce qui manque ou a changé.
4. **Dossier autonome** `Oscilloscope\` : son code (`scope\`, `launcher.py`) est aligné sur
   les sources. Son Python embarqué n'est pas modifié. Si une dépendance change, il faut
   reconstruire le dossier avec `packaging\build_embed.py` (voir [docs/README.fr.md](docs/README.fr.md)).
5. **Contrôles** : `launcher.py --check` avec chaque Python ; il doit afficher `scope OK`.

## En cas de problème

- **Journal** : `logs\oscilloscope.log`, ou `Oscilloscope\logs\oscilloscope.log` pour le
  dossier autonome. Il est horodaté et contient toutes les erreurs, y compris celles qui
  surviennent après l'ouverture de la fenêtre.
- **Console visible** : `Oscilloscope\Oscilloscope-debug.bat`.
- **« Échec de connexion » / le scope ne répond pas** (journal : `*IDN?` … délai dépassé) :
  la liaison réseau s'ouvre mais le scope ne répond plus. C'est le blocage connu de son
  interface réseau après une rafale de réglages. **Redémarrer l'oscilloscope**, fermer tout
  autre logiciel connecté au scope (EasyScopeX, une autre fenêtre PEOscillo), puis tester :
  ```powershell
  cd "$HOME\PEO-showcase"
  .\.venv\Scripts\python.exe -m scope.cli idn 10.11.13.220            # VXI-11
  .\.venv\Scripts\python.exe -m scope.cli --socket idn 10.11.13.220   # socket (celui de la GUI)
  ```
  Les deux doivent afficher `Siglent Technologies,SDS1204X-E,…`.
- **« l'exécution de scripts est désactivée »** : lancer le script avec
  `powershell -ExecutionPolicy Bypass -File .\install.ps1`, comme ci-dessus. Ce réglage ne
  vaut que pour cette commande.
- **« Python 3.12 introuvable »** : `winget install Python.Python.3.12`, puis relancer.
- **Ne pas lancer `py launcher.py` directement** : `py` choisit la version de Python la plus
  récente installée, qui peut être une version alpha. Passer par `install.ps1`, puis par
  `.venv`.
