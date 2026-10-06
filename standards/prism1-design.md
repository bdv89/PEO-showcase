# Prisme 1 : Design

## Principes fondamentaux

Ce prisme regroupe les principes de conception logicielle qui guident vers des solutions simples, maintenables et évolutives.

---

## KISS (Keep It Simple, Stupid)

**Principe** : La simplicité doit être un objectif clé de la conception. Éviter la complexité inutile.

### Application

- Écrire du code lisible et direct
- Préférer les solutions évidentes aux solutions "intelligentes"
- Éviter les optimisations prématurées
- Un développeur junior devrait comprendre le code

### Questions de critique

| Question | Si "Non" |
|----------|----------|
| Un développeur peut-il comprendre ce code en 5 minutes ? | Simplifier |
| La solution utilise-t-elle les outils les plus directs ? | Revoir l'approche |
| Peut-on expliquer l'architecture en une phrase ? | Trop complexe |

---

## Philosophie UNIX

**Principe** : Faire une seule chose, et la faire bien. Composer des outils simples.

### Les règles UNIX

1. **Une seule responsabilité** : Chaque programme/fonction fait une chose
2. **Composabilité** : Les composants peuvent se combiner
3. **Texte comme interface** : Formats simples et universels
4. **Prototypage rapide** : Construire, tester, itérer
5. **Portabilité** : Préférer la portabilité à l'efficacité

### Application

```
Mauvais : Un monolithe qui fait tout
Bon     : Des modules indépendants qui communiquent
```

### Questions de critique

| Question | Si "Non" |
|----------|----------|
| Chaque fonction a-t-elle une seule raison de changer ? | Découper |
| Les composants sont-ils réutilisables ? | Généraliser |
| Peut-on tester chaque partie indépendamment ? | Découpler |

---

## SoC (Separation of Concerns)

**Principe** : Séparer un programme en sections distinctes, chacune adressant une préoccupation séparée.

### Couches typiques

| Couche | Responsabilité |
|--------|----------------|
| Présentation | Interface utilisateur, affichage |
| Logique métier | Règles, calculs, workflows |
| Données | Persistance, accès aux données |
| Infrastructure | Logging, config, services externes |

### Application

- Ne pas mélanger HTML/CSS/JS dans le même fichier sans raison
- Séparer validation et traitement
- Isoler les dépendances externes

### Questions de critique

| Question | Si "Non" |
|----------|----------|
| Le code UI est-il séparé de la logique métier ? | Refactorer |
| Les accès données sont-ils isolés ? | Créer une couche |
| Peut-on changer une couche sans impacter les autres ? | Découpler |

---

## Rasoir d'Ockham

**Principe** : Parmi les hypothèses concurrentes, préférer celle qui fait le moins de suppositions.

### Application

- Choisir la solution avec le moins de dépendances
- Éviter les frameworks si une lib suffit
- Éviter les libs si le code natif suffit
- Éviter l'abstraction si le code concret suffit

### Hiérarchie de préférence

```
1. Code natif/standard
2. Bibliothèque légère
3. Framework complet
4. Solution custom complexe
```

### Questions de critique

| Question | Si "Non" |
|----------|----------|
| Cette dépendance est-elle vraiment nécessaire ? | Supprimer |
| Peut-on faire la même chose plus simplement ? | Simplifier |
| La solution fait-elle des suppositions non vérifiées ? | Valider |

---

## YAGNI (You Aren't Gonna Need It)

**Principe** : Ne pas implémenter de fonctionnalité tant qu'elle n'est pas nécessaire.

### Ce qu'il faut éviter

- Paramètres de configuration "au cas où"
- Abstractions pour des cas d'usage hypothétiques
- Optimisations pour des problèmes de performance inexistants
- Support de formats/protocoles non demandés

### Application

```
Mauvais : "On pourrait avoir besoin de supporter XML plus tard"
Bon     : Implémenter JSON maintenant, ajouter XML si demandé
```

### Questions de critique

| Question | Si "Oui" |
|----------|----------|
| Cette feature est-elle demandée explicitement ? | Implémenter |
| Résout-elle un problème actuel et réel ? | Implémenter |
| Est-ce "au cas où" ou "parce qu'on pourrait" ? | **Supprimer** |

---

## SOLID (si applicable)

Ces principes s'appliquent principalement à la programmation orientée objet.

### S - Single Responsibility Principle

> Une classe ne devrait avoir qu'une seule raison de changer.

**Application** : Une classe = une responsabilité.

### O - Open/Closed Principle

> Les entités doivent être ouvertes à l'extension, fermées à la modification.

**Application** : Étendre via héritage/composition, pas en modifiant le code existant.

### L - Liskov Substitution Principle

> Les objets d'une classe dérivée doivent pouvoir remplacer les objets de la classe de base.

**Application** : Les sous-classes respectent le contrat de la classe parente.

### I - Interface Segregation Principle

> Plusieurs interfaces spécifiques valent mieux qu'une interface générale.

**Application** : Interfaces petites et ciblées.

### D - Dependency Inversion Principle

> Dépendre des abstractions, pas des implémentations concrètes.

**Application** : Injection de dépendances, interfaces.

### Quand appliquer SOLID

| Contexte | SOLID applicable ? |
|----------|-------------------|
| Script bash simple | Non |
| Configuration Nix | Partiellement (S) |
| Application web | Oui |
| Bibliothèque réutilisable | Oui |
| Prototype rapide | Non (simplifier) |

---

## Checklist de critique Prisme 1

Appliquer ces questions à chaque version du TODO :

### Simplicité (KISS)

- [ ] Le code est-il lisible sans commentaires excessifs ?
- [ ] Un nouveau développeur comprendrait-il rapidement ?
- [ ] Y a-t-il du code "clever" qui pourrait être simplifié ?

### Responsabilité unique (UNIX/SoC)

- [ ] Chaque fonction fait-elle une seule chose ?
- [ ] Les préoccupations sont-elles séparées ?
- [ ] Les composants sont-ils testables indépendamment ?

### Minimalisme (Ockham)

- [ ] Chaque dépendance est-elle justifiée ?
- [ ] La solution fait-elle le minimum de suppositions ?
- [ ] Y a-t-il des alternatives plus simples ?

### Pragmatisme (YAGNI)

- [ ] Chaque feature répond-elle à un besoin actuel ?
- [ ] Y a-t-il du code "au cas où" ?
- [ ] Les abstractions sont-elles nécessaires maintenant ?

### Architecture (SOLID si OOP)

- [ ] Les classes ont-elles une seule responsabilité ?
- [ ] Le code est-il extensible sans modification ?
- [ ] Les dépendances sont-elles injectées ?

---

## Red flags

| Signal | Problème probable |
|--------|-------------------|
| "On pourrait en avoir besoin" | YAGNI violation |
| Classe/fonction > 200 lignes | SRP violation |
| > 3 niveaux d'indentation | Complexité excessive |
| Commentaire expliquant le "pourquoi" du hack | Design flaw |
| Mock complexe pour tester | Couplage fort |
| "C'est plus flexible" sans use case | Abstraction prématurée |
| Dépendance pour < 50 lignes de code | Ockham violation |

---

## Exemples de critique

### Exemple 1 : Abstraction prématurée

```python
# Mauvais - Abstraction sans besoin
class DataProcessor(ABC):
    @abstractmethod
    def process(self, data): pass

class JSONProcessor(DataProcessor):
    def process(self, data):
        return json.loads(data)

# Bon - Direct et simple
def parse_json(data):
    return json.loads(data)
```

**Critique** : L'abstraction n'est justifiée que si plusieurs types de processors existent.

### Exemple 2 : Configuration excessive

```python
# Mauvais - Configuration YAGNI
config = {
    "format": "json",  # Seul format utilisé
    "encoding": "utf-8",  # Jamais changé
    "compression": None,  # Jamais utilisé
    "retry_count": 3,  # Jamais modifié
}

# Bon - Valeurs directes
FORMAT = "json"
ENCODING = "utf-8"
```

**Critique** : Configurable ≠ utile. Hardcoder les valeurs qui ne changent pas.

### Exemple 3 : Découpage correct

```bash
# Mauvais - Script monolithique
#!/bin/bash
# 500 lignes qui font tout

# Bon - Fonctions ciblées
source lib/validation.sh
source lib/processing.sh
source lib/output.sh

main() {
    validate_input "$1"
    process_data
    generate_output
}
```

**Critique** : Le découpage permet de tester et maintenir chaque partie.
