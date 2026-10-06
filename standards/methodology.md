# Méthodologie en boucles itératives

## Principes fondamentaux

1. **Itération** : Raffiner la solution par cycles successifs
2. **Critique** : Chaque version est analysée avant progression
3. **Traçabilité** : Chaque version TODO est conservée
4. **Séparation** : Design d'abord, qualité ensuite, validation finale

---

## Boucle 1 : Design

**Objectif** : Produire une solution stable du point de vue architectural.

**Prisme appliqué** : `prism1-design.md` (KISS, UNIX, SoC, Ockham, YAGNI, SOLID)

### Étapes

1. **Analyser** la demande utilisateur
2. **Identifier** les solutions candidates
3. **Écrire** `output/TODO_v1.md` avec la solution proposée
4. **Critiquer** avec les questions du Prisme 1
5. **Évaluer** : modifications fondamentales nécessaires ?
   - **Oui** → Réviser → `TODO_v2.md` → Répéter étape 4
   - **Non** → Passer à Boucle 2

### Critères de sortie

- [ ] La solution est la plus simple possible (KISS)
- [ ] Chaque composant a une seule responsabilité (SoC)
- [ ] Aucune abstraction prématurée
- [ ] Aucune fonctionnalité spéculative (YAGNI)
- [ ] Les critiques successives ne changent plus le design fondamental

### Sortie

`output/TODO_vN.md` où N est la dernière version stable.

---

## Boucle 2 : Qualité

**Objectif** : Enrichir la solution avec les contraintes de qualité.

**Prismes appliqués** : Ceux cochés dans CLAUDE.md parmi :
- `prism-accessibility.md`
- `prism-privacy.md`
- `prism-security.md`
- `prism-test.md`
- `prism-knowledge.md`

### Étapes

1. **Lire** `output/TODO_vN.md` (sortie Boucle 1)
2. **Appliquer** chaque prisme actif séquentiellement :

| Prisme | Action |
|--------|--------|
| Accessibility | Vérifier impacts UI/UX, ajouter contraintes WCAG |
| Privacy | Vérifier gestion données, ajouter contraintes CCPA/GDPR |
| Security | Vérifier vulnérabilités, ajouter contraintes OWASP |
| Test | Définir stratégie de test, métriques de couverture |
| Knowledge | Identifier docs manquantes → télécharger dans `/docs/` |

3. **Enrichir** `output/TODO_v(N+1).md` avec les contraintes identifiées

### Critères de sortie

- [ ] Chaque prisme actif a été appliqué
- [ ] Les contraintes sont documentées dans le TODO
- [ ] La documentation nécessaire est dans `/docs/`

### Sortie

`output/TODO_v(N+1).md` enrichi avec section "Contraintes Qualité".

---

## Boucle 3 : Validation finale

**Objectif** : Vérifier la cohérence entre design et contraintes qualité.

### Étapes

1. **Reprendre** Boucle 1 sur `TODO_v(N+1).md`
2. **Vérifier** : les contraintes qualité créent-elles des conflits avec le design ?
   - **Oui** → Résoudre le conflit → Nouvelle version → Répéter
   - **Non** → Continuer
3. **Valider** : le design reste-t-il KISS malgré les contraintes ?
   - **Oui** → Passer à Exécution
   - **Non** → Simplifier → Répéter Boucle 2 si nécessaire

### Critères de sortie

- [ ] Aucun conflit entre design et contraintes qualité
- [ ] Le design reste simple et maintenable
- [ ] Toutes les contraintes sont adressées

### Sortie

`output/TODO_final.md` prêt pour exécution.

---

## Exécution

**Objectif** : Implémenter la solution validée.

### Étapes

1. **Lire** `output/TODO_final.md`
2. **Implémenter** chaque tâche séquentiellement
3. **Valider** contre les prismes au fur et à mesure
4. **Documenter** les décisions d'implémentation si écart avec le plan

### Bonnes pratiques

- Commiter après chaque tâche majeure
- Vérifier les contraintes qualité en continu
- Ne pas dévier du plan sans justification

---

## Format TODO_vN.md

```markdown
# TODO v{N} - {Nom du projet}

**Date** : {YYYY-MM-DD}
**Boucle** : {1|2|3|final}

## Contexte

{Description du problème à résoudre}

## Solution proposée

{Description de l'approche choisie}

## Tâches

- [ ] Tâche 1
- [ ] Tâche 2
- [ ] ...

## Critique Prisme 1 (si v > 1)

| Question | Réponse |
|----------|---------|
| Solution la plus simple ? | {Oui/Non + justification} |
| Abstractions prématurées ? | {Oui/Non + justification} |
| Fonctionnalités spéculatives ? | {Oui/Non + justification} |

## Contraintes Qualité (si Boucle 2 passée)

### Accessibility
{Notes ou "N/A si prisme non actif"}

### Privacy
{Notes ou "N/A si prisme non actif"}

### Security
{Notes ou "N/A si prisme non actif"}

### Test
{Stratégie de test}

### Knowledge
{Liste des docs téléchargées dans /docs/}

## Historique des versions

| Version | Date | Changements |
|---------|------|-------------|
| v1 | {date} | Version initiale |
| v2 | {date} | {description} |
```

---

## Diagramme de flux

```
                    ┌──────────────────┐
                    │  Demande user    │
                    └────────┬─────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────┐
│                    BOUCLE 1                            │
│  ┌─────────┐    ┌──────────┐    ┌─────────────┐       │
│  │ Analyse │───▶│ TODO_v1  │───▶│ Critique P1 │       │
│  └─────────┘    └──────────┘    └──────┬──────┘       │
│                                        │              │
│                    ┌───────────────────┘              │
│                    │ Modif fondamentale?              │
│                    ▼                                  │
│              ┌─────────┐                              │
│          Oui │         │ Non                          │
│    ┌─────────┤         ├─────────┐                    │
│    │         └─────────┘         │                    │
│    ▼                             ▼                    │
│ TODO_vN+1 ───────────────▶  TODO_vN stable           │
│    │                             │                    │
│    └─────────────────────────────┘                    │
└────────────────────────────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────┐
│                    BOUCLE 2                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ Accessibility│  │  Privacy   │  │  Security   │    │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘    │
│         └────────────────┼────────────────┘           │
│                          ▼                            │
│  ┌─────────────┐  ┌─────────────┐                     │
│  │    Test     │  │  Knowledge  │                     │
│  └──────┬──────┘  └──────┬──────┘                     │
│         └────────────────┘                            │
│                    │                                  │
│                    ▼                                  │
│             TODO_v(N+1) enrichi                       │
└────────────────────────────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────┐
│                    BOUCLE 3                            │
│         Reprendre Boucle 1 sur TODO enrichi           │
│                          │                            │
│                    Conflits ?                         │
│                    │       │                          │
│                Oui ▼       ▼ Non                      │
│             Résoudre    TODO_final                    │
└────────────────────────────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────┐
│                   EXÉCUTION                            │
│         Implémenter TODO_final séquentiellement       │
└────────────────────────────────────────────────────────┘
```
