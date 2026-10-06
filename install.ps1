<#
.SYNOPSIS
  Installe ou met à jour l'oscilloscope PEO. Relançable sans risque : chaque étape ne
  fait que ce qui manque (script idempotent).

.DESCRIPTION
  1. Code à jour : « git pull » si ce dossier est un dépôt git.
  2. Environnement Python (.venv) en Python 3.12 : créé s'il manque, recréé s'il est
     dans une autre version (ex. 3.15 alpha, où h5py ne s'installe pas).
  3. Dépendances (requirements.txt) : pip n'installe que ce qui manque ou a changé.
  4. Dossier Windows autonome (Oscilloscope\, celui du .bat) : son code (scope\,
     launcher.py) est aligné sur les sources.
  5. Contrôle : « launcher.py --check » avec chaque Python (doit afficher « scope OK »).

.PARAMETER Recreer
  Supprime et recrée le .venv même s'il est dans la bonne version.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\install.ps1
#>
param([switch]$Recreer)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$PythonVersion = "3.12"
$Venv = Join-Path $PSScriptRoot ".venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$Autonome = Join-Path $PSScriptRoot "Oscilloscope"

function Etape($texte) { Write-Host "`n== $texte" -ForegroundColor Cyan }
function Ok($texte) { Write-Host "   OK  $texte" -ForegroundColor Green }
function Echec($texte) { Write-Host "   ERREUR  $texte" -ForegroundColor Red; exit 1 }
function Verifier($etape) { if ($LASTEXITCODE -ne 0) { Echec "$etape (code $LASTEXITCODE)" } }

# 1. Code à jour --------------------------------------------------------------------
Etape "Code source"
if (Test-Path (Join-Path $PSScriptRoot ".git")) {
    git pull --ff-only
    Verifier "git pull (modifications locales ? les valider ou les mettre de côté)"
    Ok "code à jour"
} else {
    Ok "pas un dépôt git : code laissé tel quel"
}

# 2. Environnement Python ----------------------------------------------------------
Etape "Environnement Python $PythonVersion (.venv)"
$pyExe = & py "-$PythonVersion" -c "import sys; print(sys.executable)" 2>$null
if ($LASTEXITCODE -ne 0 -or -not $pyExe) {
    Echec "Python $PythonVersion introuvable. L'installer : winget install Python.Python.$PythonVersion"
}
if (Test-Path $VenvPython) {
    $actuelle = & $VenvPython -c "import sys; print('%d.%d' % sys.version_info[:2])"
    if ($Recreer -or $actuelle -ne $PythonVersion) {
        Write-Host "   .venv en Python $actuelle : recréation en $PythonVersion"
        Remove-Item -Recurse -Force $Venv
    }
}
if (-not (Test-Path $VenvPython)) {
    & py "-$PythonVersion" -m venv $Venv
    Verifier "création du .venv"
    Ok ".venv créé ($pyExe)"
} else {
    Ok ".venv déjà en Python $PythonVersion"
}

# 3. Dépendances -------------------------------------------------------------------
Etape "Dépendances (requirements.txt)"
& $VenvPython -m pip install --disable-pip-version-check --quiet --upgrade pip
Verifier "mise à jour de pip"
& $VenvPython -m pip install --disable-pip-version-check --quiet -r requirements.txt
Verifier "installation des dépendances"
Set-Content -Path (Join-Path $Venv ".ready") -Value "ok" -Encoding utf8  # repère du lanceur
Ok "dépendances à jour"

# 4. Dossier Windows autonome ------------------------------------------------------
Etape "Dossier Windows autonome (Oscilloscope\)"
$autonomePython = Join-Path $Autonome "python\python.exe"
if (Test-Path $autonomePython) {
    robocopy (Join-Path $PSScriptRoot "scope") (Join-Path $Autonome "scope") /MIR /XD __pycache__ /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { Echec "copie de scope\ (robocopy, code $LASTEXITCODE)" }
    Copy-Item (Join-Path $PSScriptRoot "launcher.py") $Autonome -Force
    Ok "code aligné sur les sources (scope\, launcher.py)"
} else {
    Ok "absent (normal après un clone) : zip Windows dans les Releases GitHub, ou packaging\build_embed.py"
}

# 5. Contrôles ---------------------------------------------------------------------
Etape "Contrôles"
& $VenvPython launcher.py --check
Verifier "contrôle du .venv"
if (Test-Path $autonomePython) {
    & $autonomePython (Join-Path $Autonome "launcher.py") --check
    Verifier "contrôle du dossier autonome"
}
Write-Host "`nInstallation à jour." -ForegroundColor Green
Write-Host "  Lancer depuis les sources : .\.venv\Scripts\python.exe launcher.py"
if (Test-Path $autonomePython) { Write-Host "  Lancer le dossier autonome : Oscilloscope\Oscilloscope.bat" }
exit 0
