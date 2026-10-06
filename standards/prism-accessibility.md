# Prisme Accessibility

## Exigences de validation

**OBLIGATOIRE** : Toutes les vérifications d'accessibilité doivent passer avant toute affirmation de production-readiness.

### Statut du gate

- **100% de conformité** avec WCAG 2.2 Level AA est OBLIGATOIRE
- Les résultats de validation doivent être vérifiés et documentés
- Aucune affirmation de production-readiness sans confirmation explicite

---

## Conformité WCAG 2.2 Level AA

### 1. Perceivable (Perceptible)

#### 1.1 Text Alternatives

- **Images** : Toutes les images ont un alt text approprié ou sont marquées comme décoratives
- **Images complexes** : Charts, graphiques et diagrammes ont des descriptions détaillées
- **Images fonctionnelles** : Images utilisées comme boutons/liens ont un alt text descriptif
- **Texte dans images** : Éviter le texte dans les images ; si nécessaire, fournir une alternative
- **Audio/Vidéo** : Le contenu audio non-verbal a des alternatives textuelles

#### 1.2 Time-based Media

- **Captions** : Tout contenu vidéo pré-enregistré a des sous-titres précis
- **Live Captions** : Les streams vidéo live fournissent des sous-titres en temps réel
- **Audio Descriptions** : Le contenu vidéo inclut des descriptions audio pour l'information visuelle
- **Transcripts** : Le contenu audio-only a des transcriptions complètes

#### 1.3 Adaptable

- **Structure sémantique** : Hiérarchie HTML correcte (h1-h6) et landmarks
- **Ordre de lecture** : Le contenu maintient un ordre logique quand linéarisé
- **Form Labels** : Tous les inputs ont des labels programmatiquement associés
- **Instructions** : Les instructions de formulaire sont associées aux contrôles
- **Tables** : Les tables de données utilisent des headers, captions et summary appropriés

#### 1.4 Distinguishable

- **Color Contrast** : Minimum 4.5:1 pour texte normal, 3:1 pour grand texte (18pt+ ou 14pt+ bold)
- **Enhanced Contrast** : Cible 7:1 pour texte normal, 4.5:1 pour grand texte (Level AAA)
- **Color Independence** : L'information n'est pas véhiculée par la couleur seule
- **Audio Control** : L'audio auto-play peut être pausé, arrêté ou muté
- **Text Resize** : Le texte peut être redimensionné à 200% sans perte de fonctionnalité
- **Images of Text** : Éviter les images de texte sauf pour logos ou graphiques essentiels

### 2. Operable (Utilisable)

#### 2.1 Keyboard Accessible

- **Keyboard Navigation** : Toutes les fonctionnalités accessibles via clavier
- **Focus Management** : Ordre de tabulation logique et indicateurs de focus visibles
- **Keyboard Shortcuts** : Pas de raccourcis clavier conflictuels
- **Character Key Shortcuts** : Les raccourcis à caractère unique peuvent être désactivés/remappés
- **Focus Order** : L'ordre de tabulation suit la séquence logique du contenu

#### 2.2 Enough Time

- **Time Limits** : Les utilisateurs peuvent étendre, ajuster ou désactiver les limites de temps
- **Auto-refresh** : Le contenu auto-refresh peut être pausé ou contrôlé
- **Session Timeout** : Les utilisateurs sont avertis avant l'expiration avec option d'extension
- **Interruptions** : Les utilisateurs peuvent reporter ou supprimer les interruptions non-urgentes
- **Re-authentication** : Les données sont préservées quand la session expire pendant un formulaire

#### 2.3 Seizures and Physical Reactions

- **Flashing Content** : Aucun contenu ne clignote plus de 3 fois par seconde
- **Animation Control** : Les utilisateurs peuvent désactiver les animations non-essentielles
- **Motion Sensitivity** : Respecter la media query CSS `prefers-reduced-motion`
- **Parallax Scrolling** : Fournir une option pour désactiver les effets parallaxe
- **Auto-playing Media** : Le contenu auto-play peut être pausé ou arrêté

#### 2.4 Navigable

- **Skip Links** : Liens pour sauter vers le contenu principal et autres sections
- **Page Titles** : Titres de page descriptifs et uniques
- **Link Purpose** : Le texte des liens décrit clairement la destination ou fonction
- **Multiple Navigation** : Plusieurs moyens de localiser les pages (menu, recherche, sitemap)
- **Headings and Labels** : Headings et form labels descriptifs
- **Focus Visible** : Le focus clavier est clairement visible

#### 2.5 Input Modalities

- **Pointer Gestures** : Tous les gestes multipoint/path-based ont une alternative single-pointer
- **Pointer Cancellation** : Activation sur up-event ou fonctionnalité abort/undo
- **Label in Name** : Le nom accessible contient le texte visible du label
- **Motion Actuation** : Les triggers de mouvement device peuvent être désactivés
- **Target Size** : Cibles tactiles minimum 24x24 CSS pixels (44x44 recommandé)

### 3. Understandable (Compréhensible)

#### 3.1 Readable

- **Language** : La langue de la page est identifiée programmatiquement
- **Language Changes** : Les changements de langue dans le contenu sont identifiés
- **Pronunciation** : La prononciation est fournie pour les mots ambigus
- **Abbreviations** : La forme étendue ou définition est fournie pour les abréviations
- **Reading Level** : Le contenu est écrit à un niveau de lecture approprié (cible 9ème année)

#### 3.2 Predictable

- **Consistent Navigation** : Les mécanismes de navigation sont cohérents entre les pages
- **Consistent Identification** : Les composants d'interface sont identifiés de façon cohérente
- **Context Changes** : Les changements de contexte se font uniquement sur demande utilisateur
- **Error Prevention** : Les engagements légaux/financiers/données sont réversibles/confirmables
- **Help** : L'aide contextuelle est disponible

#### 3.3 Input Assistance

- **Error Identification** : Les erreurs de formulaire sont clairement identifiées et décrites
- **Error Suggestions** : Des suggestions sont fournies pour corriger les erreurs d'input
- **Error Prevention** : Les soumissions importantes nécessitent confirmation ou review
- **Accessible Authentication** : Les méthodes d'auth ne reposent pas uniquement sur des tests cognitifs
- **Redundant Entry** : Les informations précédemment entrées sont pré-remplies ou disponibles

### 4. Robust (Robuste)

#### 4.1 Compatible

- **Valid Code** : Le HTML est valide et utilise une sémantique appropriée
- **Name, Role, Value** : Tous les composants UI exposent name, role, state et value
- **Status Messages** : Les changements de statut importants sont annoncés aux screen readers
- **Custom Controls** : Les composants UI custom implémentent correctement ARIA
- **Progressive Enhancement** : La fonctionnalité core fonctionne sans JavaScript

---

## Tests automatisés requis

### Playwright Accessibility Testing

- **axe-playwright Integration** : Toutes les pages testées avec le moteur axe
- **Automated Scans** : Tests a11y automatisés dans le pipeline CI/CD
- **Custom Rules** : Règles d'accessibilité spécifiques au projet configurées
- **Regression Testing** : Tests de régression visuelle pour les features d'accessibilité
- **Performance Impact** : Les features d'accessibilité n'impactent pas significativement la performance

### Outils et couverture

| Outil | Cible | Red Flag |
|-------|-------|----------|
| **Lighthouse A11y** | 95+ | < 90 🚨 |
| **axe-core Violations** | 0 | > 0 🔥 |
| **Pa11y Errors** | 0 | > 0 ⚠️ |
| **Color Contrast** | 100% | < 95% 📋 |

---

## Tests manuels requis

### Screen Reader Testing

- **NVDA** : Test avec NVDA sur Windows (screen reader gratuit)
- **JAWS** : Test avec JAWS si disponible (le plus courant en entreprise)
- **VoiceOver** : Test avec VoiceOver sur macOS/iOS
- **TalkBack** : Test avec TalkBack sur Android
- **Narrator** : Test avec Windows Narrator

### Keyboard Navigation Testing

- **Tab Navigation** : Navigation clavier complète sans souris
- **Skip Links** : Test de la fonctionnalité skip navigation
- **Focus Management** : Vérifier que le focus se déplace logiquement
- **Keyboard Shortcuts** : Test de tous les raccourcis et access keys
- **Modal Dialogs** : Test de la navigation clavier dans les modals et popups

### Visual Testing

- **High Contrast Mode** : Test en mode High Contrast Windows
- **Browser Zoom** : Test à 200% de zoom navigateur
- **Custom Colors** : Test avec des schémas de couleurs personnalisés
- **Dark Mode** : Test de l'accessibilité et du contraste en mode sombre
- **Reduced Motion** : Test avec `prefers-reduced-motion` activé

---

## Standards CLI et Script

### Accessibilité CLI

- **Screen Reader Compatibility** : La sortie CLI fonctionne avec les screen readers
- **Color Independence** : Ne pas se fier uniquement à la couleur pour l'information importante
- **High Contrast** : Support des thèmes terminal high contrast
- **Text Formatting** : Utiliser le formatage sémantique (bold/italic) plutôt que couleur seule
- **Progress Indicators** : Fournir des indicateurs de progression text-based pour les longues opérations
- **Error Messages** : Messages d'erreur clairs et descriptifs avec solutions suggérées
- **Help Text** : Documentation d'aide complète avec exemples
- **Keyboard Navigation** : Support des raccourcis clavier terminal standard

### Sortie de script

- **Structured Output** : Formatage cohérent pour la sortie de script
- **Status Messages** : Indicateurs de statut clairs (SUCCESS, ERROR, WARNING)
- **Progress Feedback** : Indicateurs de progression text-based pour les scripts longs
- **Error Handling** : Messages d'erreur descriptifs avec informations actionnables
- **Documentation** : Documentation accessible avec exemples d'utilisation
- **Logging** : Logging structuré compatible avec les technologies d'assistance

---

## Métriques et seuils

### Tests automatisés

| Métrique | Cible | Tolérance | Red Flag |
|----------|-------|-----------|----------|
| **Lighthouse A11y** | 95+ | 90-94 | < 90 🚨 |
| **axe-core Violations** | 0 | 0 | > 0 🔥 |
| **Pa11y Errors** | 0 | 0 | > 0 ⚠️ |
| **Color Contrast** | 100% | 95%+ | < 95% 📋 |

### Tests manuels

| Type de test | Cible | Tolérance | Red Flag |
|--------------|-------|-----------|----------|
| **Screen Reader Testing** | 100% UI | 90%+ | < 80% 🚨 |
| **Keyboard Navigation** | 100% fonctionnel | 95%+ | < 90% 🔥 |
| **Mobile A11y Testing** | 100% UI mobile | 90%+ | < 80% ⚠️ |
| **High Contrast Testing** | 100% lisible | 95%+ | < 90% 📋 |

### Conformité WCAG 2.2

| Level | Cible | Tolérance | Red Flag |
|-------|-------|-----------|----------|
| **Level A** | 100% | 100% | < 100% 🚨 |
| **Level AA** | 100% | 100% | < 100% 🔥 |
| **Level AAA** | 50% | 30%+ | < 20% 📋 |

---

## Guidelines de communication

### NE JAMAIS affirmer la conformité accessibilité sans :

- Confirmation explicite que TOUS les tests automatisés passent
- Preuves des résultats de tests manuels
- Vérification de la conformité WCAG 2.2 Level AA
- Documentation des tests screen reader et clavier
- Confirmation de la couverture des tests d'accessibilité

### Au lieu de dire "accessible" ou "WCAG compliant", utiliser un langage spécifique :

- "Tests automatisés passants mais nécessite [tests manuels] avant production"
- "Conforme WCAG 2.2 Level A mais nécessite [validation Level AA] pour production"
- "Compatible screen reader mais nécessite [test navigation clavier] validation"
- "Baseline accessibilité atteinte mais nécessite [tests utilisateur avec handicaps] avant production"
- "Outils A11y passants mais nécessite [audit accessibilité] pour conformité complète"

---

## Checklist d'implémentation

### Exigences pré-production

- [ ] Tous les tests automatisés passent avec 100% conformité
- [ ] Résultats de validation documentés et vérifiés
- [ ] Conformité WCAG 2.2 Level AA confirmée
- [ ] Aucun finding bloquant le déploiement production

### Vérification WCAG 2.2 Level AA

#### 1. Perceivable

- [ ] **Text Alternatives** : Toutes images ont alt text approprié ou marquées décoratives
- [ ] **Captions** : Contenu vidéo pré-enregistré a des sous-titres précis
- [ ] **Audio Descriptions** : Contenu vidéo inclut descriptions audio
- [ ] **Color Contrast** : Minimum 4.5:1 texte normal, 3:1 grand texte
- [ ] **Text Resize** : Texte redimensionnable à 200% sans perte de fonctionnalité
- [ ] **Semantic Structure** : Hiérarchie HTML correcte (h1-h6) et landmarks
- [ ] **Form Labels** : Tous les inputs ont des labels programmatiquement associés

#### 2. Operable

- [ ] **Keyboard Navigation** : Toutes fonctionnalités accessibles via clavier
- [ ] **Focus Management** : Ordre de tabulation logique et indicateurs de focus visibles
- [ ] **Time Limits** : Utilisateurs peuvent étendre, ajuster ou désactiver les limites
- [ ] **Seizure Prevention** : Aucun contenu clignote plus de 3 fois/seconde
- [ ] **Skip Links** : Liens pour sauter vers contenu principal et autres sections
- [ ] **Page Titles** : Titres de page descriptifs et uniques
- [ ] **Target Size** : Cibles tactiles minimum 24x24 CSS pixels

#### 3. Understandable

- [ ] **Language** : Langue de page identifiée programmatiquement
- [ ] **Consistent Navigation** : Mécanismes de navigation cohérents entre pages
- [ ] **Error Identification** : Erreurs de formulaire clairement identifiées et décrites
- [ ] **Error Suggestions** : Suggestions fournies pour corriger erreurs d'input
- [ ] **Context Changes** : Changements de contexte uniquement sur demande utilisateur

#### 4. Robust

- [ ] **Valid Code** : HTML valide avec sémantique appropriée
- [ ] **Name, Role, Value** : Tous composants UI exposent name, role, state, value
- [ ] **Status Messages** : Changements de statut importants annoncés aux screen readers
- [ ] **Progressive Enhancement** : Fonctionnalité core fonctionne sans JavaScript

### Validation tests automatisés

- [ ] **axe-playwright** : Toutes pages testées avec zéro violations
- [ ] **Lighthouse Accessibility** : Score de 95+ atteint
- [ ] **Pa11y** : Tests command-line complétés avec zéro erreurs
- [ ] **Color Contrast** : 100% conformité avec exigences de contraste
- [ ] **Custom Rules** : Règles spécifiques au projet passantes
- [ ] **CI/CD Integration** : Tests a11y automatisés dans pipeline

### Tests manuels complétés

#### Screen Reader Testing

- [ ] **NVDA** : Testé avec NVDA sur Windows
- [ ] **JAWS** : Testé avec JAWS (si disponible)
- [ ] **VoiceOver** : Testé avec VoiceOver sur macOS/iOS
- [ ] **TalkBack** : Testé avec TalkBack sur Android
- [ ] **Narrator** : Testé avec Windows Narrator

#### Keyboard Navigation Testing

- [ ] **Tab Navigation** : Navigation clavier complète sans souris
- [ ] **Skip Links** : Fonctionnalité skip navigation testée
- [ ] **Focus Management** : Focus se déplace logiquement dans interface
- [ ] **Keyboard Shortcuts** : Tous raccourcis et access keys testés
- [ ] **Modal Dialogs** : Navigation clavier dans modals et popups testée

#### Visual and Environmental Testing

- [ ] **High Contrast Mode** : Testé en mode High Contrast Windows
- [ ] **Browser Zoom** : Testé à 200% zoom navigateur
- [ ] **Custom Colors** : Testé avec schémas de couleurs personnalisés
- [ ] **Dark Mode** : Accessibilité et contraste mode sombre vérifiés
- [ ] **Reduced Motion** : Testé avec prefers-reduced-motion activé

### CLI et Script (si applicable)

- [ ] **Screen Reader Compatibility** : Sortie CLI fonctionne avec screen readers
- [ ] **Color Independence** : Information importante non véhiculée par couleur seule
- [ ] **High Contrast Support** : Supporte thèmes terminal high contrast
- [ ] **Text Formatting** : Formatage sémantique utilisé (bold/italic vs couleur seule)
- [ ] **Progress Indicators** : Indicateurs de progression text-based implémentés
- [ ] **Error Messages** : Messages d'erreur clairs et descriptifs avec solutions
- [ ] **Help Documentation** : Texte d'aide complet et accessible

### Validation métriques

- [ ] **Lighthouse A11y Score** : 95+ atteint
- [ ] **Screen Reader Testing** : 100% UI testée
- [ ] **Keyboard Navigation** : 100% couverture fonctionnelle
- [ ] **Mobile A11y Testing** : 100% UI mobile testée
- [ ] **High Contrast Testing** : 100% lisible en mode high contrast
- [ ] Toutes les métriques d'accessibilité atteignent les seuils définis
- [ ] Aucun indicateur red flag présent

### Documentation et sign-off

- [ ] **Accessibility Statement** : Déclaration d'accessibilité publique publiée
- [ ] **Testing Results** : Résultats documentés de tous les tests d'accessibilité
- [ ] **Known Issues** : Liste des problèmes connus avec timeline de remédiation
- [ ] **User Guides** : Documentation des features d'accessibilité
- [ ] **Developer Guidelines** : Standards de codage accessibilité documentés
- [ ] **Feedback Process** : Processus pour signaler les problèmes d'accessibilité établi
- [ ] Review sign-off obtenu de l'équipe/expert accessibilité
- [ ] Tests utilisateur avec personnes handicapées complétés (si possible)

---

## Principes clés

- L'accessibilité est intégrée dès le départ, pas ajoutée après coup
- Toutes les features d'accessibilité doivent être testées avec de vraies technologies d'assistance
- Les tests automatisés détectent ~30% des problèmes ; les tests manuels sont essentiels
- Les utilisateurs handicapés devraient être impliqués dans les tests quand possible
- L'accessibilité bénéficie à tous, pas seulement aux utilisateurs handicapés
- La conformité légale est le standard minimum, pas l'objectif
- L'accessibilité est un processus continu, pas une checklist unique
- Performance et accessibilité doivent être équilibrées, pas échangées
- Le design inclusif crée de meilleures expériences pour tous
- La documentation d'accessibilité aide les utilisateurs à découvrir et utiliser les features
