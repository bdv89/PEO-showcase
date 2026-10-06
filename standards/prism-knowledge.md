# Prisme Knowledge

## Objectif

Identifier, télécharger et organiser la documentation nécessaire pour implémenter la solution. Ce prisme assure que toutes les informations techniques requises sont disponibles localement avant l'exécution.

---

## Quand télécharger de la documentation

### Déclencher le téléchargement si :

| Situation | Action |
|-----------|--------|
| Utilisation d'un package/lib non familier | Télécharger la doc officielle |
| API externe à intégrer | Télécharger la référence API |
| Framework avec conventions spécifiques | Télécharger le guide de démarrage |
| Syntaxe/fonctionnalités du langage incertaines | Télécharger la référence du langage |
| Protocole/format de données à implémenter | Télécharger la spécification |

### Ne pas télécharger si :

| Situation | Raison |
|-----------|--------|
| Langage/outil bien maîtrisé | Connaissances suffisantes |
| Bibliothèque standard du langage | Documentation intégrée |
| Code déjà documenté dans le projet | Éviter la duplication |
| Concepts généraux (algorithmique, patterns) | Trop large, pas spécifique |

---

## Structure du dossier `/docs/`

Les fichiers sont stockés à plat dans `/docs/` avec un nommage explicite.

### Convention de nommage

```
{source}_{sujet}_{version}.md
```

**Exemples** :
- `npm_express_4.18.md`
- `python_requests_2.31.md`
- `api_github_v3.md`
- `spec_json-schema_draft-07.md`
- `nix_flakes_guide.md`

### Catégories de sources

| Préfixe | Type de documentation |
|---------|----------------------|
| `npm_` | Package npm/Node.js |
| `pypi_` | Package Python (PyPI) |
| `cargo_` | Crate Rust (crates.io) |
| `nix_` | Documentation NixOS/Nix |
| `api_` | Documentation d'API externe |
| `spec_` | Spécification technique (RFC, standards) |
| `lang_` | Référence de langage |
| `tool_` | Outil de développement |

---

## Sources autorisées

### Documentation officielle uniquement

| Source | Autorité |
|--------|----------|
| docs.python.org | Python officiel |
| nodejs.org/docs | Node.js officiel |
| doc.rust-lang.org | Rust officiel |
| nixos.org/manual | NixOS officiel |
| developer.mozilla.org | Web standards (MDN) |
| {package}.readthedocs.io | Packages avec RTD |
| github.com/{repo}/wiki | Documentation projet |
| {api}.{vendor}.com/docs | APIs officielles |

### Sources à éviter

| Source | Raison |
|--------|--------|
| Stack Overflow | Réponses fragmentées, potentiellement obsolètes |
| Blogs personnels | Non officiel, non maintenu |
| Medium/Dev.to | Qualité variable, pas de garantie |
| Tutoriels YouTube | Non extractible en texte |
| Forums/Reddit | Opinions, pas documentation |

---

## Format de la documentation téléchargée

### Structure recommandée

```markdown
# {Nom du package/API} - Documentation

**Source** : {URL officielle}
**Version** : {version documentée}
**Date de téléchargement** : {YYYY-MM-DD}

## Résumé

{Description courte du package/API et son usage principal}

## Installation

{Instructions d'installation}

## Usage de base

{Exemples de code essentiels}

## API Reference

{Fonctions/méthodes principales avec signatures}

## Configuration

{Options de configuration importantes}

## Exemples

{Exemples pratiques tirés de la documentation}

## Notes importantes

{Gotchas, limitations, breaking changes}
```

---

## Workflow de téléchargement

### 1. Identifier les besoins

Pendant la Boucle 2, pour chaque tâche du TODO :

```
Pour chaque tâche :
  - Lister les packages/APIs utilisés
  - Vérifier si la doc existe dans /docs/
  - Si non : télécharger
```

### 2. Télécharger la documentation

**Méthode** : Utiliser `WebFetch` pour récupérer la documentation officielle.

**Contenu à extraire** :
- Getting started / Quick start
- API Reference (fonctions principales)
- Configuration / Options
- Exemples de code
- Breaking changes / Migration guide

### 3. Documenter dans le TODO

Ajouter dans la section "Knowledge" du TODO :

```markdown
## Knowledge

### Documentation téléchargée
- `npm_express_4.18.md` : Framework web Node.js
- `api_stripe_v2023.md` : API de paiement

### Documentation existante utilisée
- `npm_lodash_4.17.md` (déjà présent)

### Notes
- Express 4.x requiert Node 14+
- Stripe webhook signature nécessite raw body
```

---

## Checklist d'implémentation

### Avant la Boucle 2

- [ ] Lister tous les packages/APIs du TODO_v1
- [ ] Vérifier la présence dans `/docs/`
- [ ] Identifier les docs manquantes

### Pendant la Boucle 2

- [ ] Télécharger chaque doc manquante
- [ ] Respecter le format standardisé
- [ ] Nommer selon la convention
- [ ] Vérifier que la version correspond

### Validation

- [ ] Chaque package/API du TODO a sa doc dans `/docs/`
- [ ] Les docs sont à jour (< 6 mois ou version actuelle)
- [ ] Les exemples de code sont testables
- [ ] Les breaking changes sont documentés si migration

---

## Métriques

| Métrique | Cible | Red Flag |
|----------|-------|----------|
| **Couverture** | 100% des packages/APIs | < 80% |
| **Fraîcheur** | < 6 mois | > 1 an |
| **Format** | 100% respecté | Non standardisé |
| **Source** | 100% officielle | Sources non officielles |

---

## Exemples

### Exemple 1 : Nouveau package npm

**Situation** : Le TODO mentionne l'utilisation de `zod` pour la validation.

**Action** :
1. Vérifier si `npm_zod_*.md` existe dans `/docs/`
2. Si non, télécharger depuis zod.dev
3. Créer `docs/npm_zod_3.22.md`

**Contenu** :
```markdown
# Zod - Documentation

**Source** : https://zod.dev/
**Version** : 3.22
**Date** : 2026-03-02

## Résumé
Zod is a TypeScript-first schema declaration and validation library.

## Installation
```bash
npm install zod
```

## Usage de base
```typescript
import { z } from "zod";

const User = z.object({
  name: z.string(),
  age: z.number().positive(),
});

type User = z.infer<typeof User>;
```

## API Reference

### Primitives
- `z.string()` - String validation
- `z.number()` - Number validation
- `z.boolean()` - Boolean validation
...
```

### Exemple 2 : API externe

**Situation** : Intégration avec l'API GitHub pour récupérer des issues.

**Action** :
1. Vérifier si `api_github_v3.md` existe
2. Télécharger la partie "Issues" de la doc GitHub API
3. Créer `docs/api_github_issues_v3.md`

### Exemple 3 : Configuration NixOS

**Situation** : Configuration d'un service systemd via NixOS.

**Action** :
1. Vérifier si `nix_services_systemd.md` existe
2. Télécharger depuis nixos.org/manual
3. Focus sur `systemd.services` et les options

---

## Intégration avec les autres prismes

### Avec Prisme Security

- Documenter les security considerations des packages
- Vérifier les security advisories
- Noter les versions avec vulnérabilités connues

### Avec Prisme Test

- Documenter les méthodes de test recommandées
- Inclure les fixtures/mocks fournis par le package
- Noter les testing utilities disponibles

### Avec Prisme Accessibility

- Documenter les features d'accessibilité des composants UI
- Inclure les ARIA attributes supportés
- Noter les keyboard navigation patterns

---

## Maintenance

### Mise à jour de la documentation

- **Déclencheur** : Nouvelle version majeure du package
- **Action** : Créer nouveau fichier avec version, archiver l'ancien
- **Historique** : Garder les 2 dernières versions majeures

### Nettoyage

- **Fréquence** : Après chaque projet terminé
- **Action** : Supprimer les docs non utilisées dans les 3 derniers mois
- **Exception** : Garder les docs de packages fréquemment utilisés

---

## Principes clés

1. **Documentation officielle seulement** - Pas de sources non vérifiées
2. **À plat dans /docs/** - Pas de hiérarchie complexe
3. **Nommage explicite** - Source, sujet, version
4. **Format standardisé** - Structure cohérente
5. **Versionné** - Correspondance avec le package utilisé
6. **Minimal mais complet** - L'essentiel, pas tout
7. **Exemples pratiques** - Code exécutable
8. **Notes de migration** - Breaking changes documentés
