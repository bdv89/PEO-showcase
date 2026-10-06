# CLAUDE.md - Standards Méthodologiques

> **Version** : 1.1
> **Date** : 2026-03-02

## Vue d'ensemble

Ce système définit une méthodologie de **développement collaboratif** en boucles itératives. L'approche combine :

1. **Dialogue actif** : Clarification des requirements avant toute implémentation
2. **TDD** : Tests écrits AVANT le code
3. **Prismes d'analyse** : Validation qualité à chaque boucle
4. **Validation continue** : Monitoring du scope et de la complexité

## Prismes actifs pour ce projet

Cocher les prismes à appliquer :

- [x] prism1-design (obligatoire)
- [ ] prism-security
- [ ] prism-accessibility
- [ ] prism-privacy
- [x] prism-test
- [x] prism-knowledge

## Référence rapide

### Protocoles (obligatoires)

| Fichier | Description |
|---------|-------------|
| [collaborative-protocol.md](standards/collaborative-protocol.md) | **Dialogue, TDD, validation continue** |
| [methodology.md](standards/methodology.md) | Workflow en boucles |

### Prismes (selon projet)

| Fichier | Description |
|---------|-------------|
| [prism1-design.md](standards/prism1-design.md) | KISS, UNIX, SoC, Ockham, YAGNI, SOLID |
| [prism-accessibility.md](standards/prism-accessibility.md) | WCAG 2.2 AA complet |
| [prism-privacy.md](standards/prism-privacy.md) | CCPA/CPRA, GDPR complet |
| [prism-security.md](standards/prism-security.md) | OWASP Top 10, SOC 2 complet |
| [prism-test.md](standards/prism-test.md) | Unit, Integration, E2E complet |
| [prism-knowledge.md](standards/prism-knowledge.md) | Gestion documentation |

## Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                   PHASE 0 : CLARIFICATION                       │
│  Questions → Compréhension → Accord sur le scope               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                        BOUCLE 1 : DESIGN                        │
│  Prisme 1 → TODO_v1 → Critique → TODO_vN (stable)              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                       BOUCLE 2 : QUALITÉ                        │
│  Prismes actifs → Enrichir TODO_v(N+1)                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    BOUCLE 3 : VALIDATION                        │
│  Reprendre Boucle 1 → Résoudre conflits → TODO_final           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     EXÉCUTION (TDD)                             │
│  Pour chaque tâche : RED → GREEN → REFACTOR                    │
└─────────────────────────────────────────────────────────────────┘
```

## Dossiers

| Dossier | Contenu |
|---------|---------|
| `standards/` | Définitions des prismes |
| `docs/` | Documentation téléchargée (packages, APIs, etc.) |
| `output/` | Fichiers TODO_vN.md générés |

## Utilisation

### Option 1 : Cocher les prismes ci-dessus

Modifier la section "Prismes actifs" en début de fichier.

### Option 2 : Directive en session

```
/prismes: design, security, test, knowledge
```

### Option 3 : Spécifier dans la demande

> "Implémente X en appliquant les prismes design, security et test"

## Comportement attendu

### Priorités

```
Clarté       > Cleverness
Simplicité   > Flexibilité
Besoins actuels > Possibilités futures
Explicite    > Implicite
```

### Patterns interdits

| Ne jamais faire | Raison |
|-----------------|--------|
| Features "au cas où" | YAGNI |
| Abstractions sans usage | Over-engineering |
| Mélanger responsabilités | SRP violation |
| Implémenter le futur | Scope creep |
| Optimiser sans mesurer | Premature optimization |

### Validation continue

Pendant l'exécution, surveiller et corriger immédiatement :
- **Scope creep** → Revenir aux requirements
- **Complexité excessive** → Simplifier
- **Test qui échoue** → STOP et corriger

## Notes

- **Phase 0 (clarification)** et **Prisme 1 (design)** sont toujours obligatoires
- Les **TODO_vN.md** sont versionnés pour traçabilité
- La **documentation** est téléchargée dans `/docs/` à plat
- **TDD** : Tests écrits AVANT le code pendant l'exécution
- **Langue** : Structure française, termes techniques anglais
