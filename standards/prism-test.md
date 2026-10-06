# Prisme Test

## Exigences d'exécution des tests

**OBLIGATOIRE** : TOUS les tests unitaires, d'intégration et end-to-end DOIVENT passer avant toute affirmation de production-readiness.

### Statut de la suite de tests

- **100% de taux de réussite** sur tous les tests unitaires, d'intégration et end-to-end est OBLIGATOIRE
- Les résultats d'exécution des tests doivent être vérifiés et documentés
- Aucune affirmation de production-readiness sans confirmation de tests explicite

---

## Standards de tests unitaires

### Métriques de qualité du code

| Métrique | Cible | Red Flag | Action |
|----------|-------|----------|--------|
| **Line Coverage** | 70-80% | < 50% | Augmenter la couverture |
| **Branch Coverage** | 80-90% | < 60% | Focus sur les classes logic-heavy |
| **Cyclomatic Complexity** | < 10 | > 15 | Refactorer les grandes méthodes |
| **CRAP Score** | < 15 (< 10 excellent) | > 30 | Refactoring immédiat requis |

### CRAP Score

**Formule** : `CRAP = CC² × (1 - Coverage%)³ + CC`

- < 10 : Excellent
- 10-15 : Acceptable
- 15-30 : À améliorer
- > 30 : Dangereux - refactoring immédiat requis

### Exigences de qualité des tests

Chaque fonction/méthode doit avoir des tests pour :

- **Happy path** : Scénarios de succès normaux
- **Error conditions** : Conditions d'erreur et edge cases
- **Input validation** : Validation d'input et conditions limites
- **Null/undefined/empty** : Gestion des valeurs null, undefined et vides

### Standards d'implémentation des tests

- **Test Isolation** : Les tests doivent être indépendants et ne pas dépendre de dépendances externes
- **Mock Usage** : Services externes, bases de données et APIs doivent être correctement mockés
- **Naming Convention** : Noms de tests descriptifs indiquant ce qui est testé et le résultat attendu
- **Arrange-Act-Assert** : Structure claire des tests (Given-When-Then)

---

## Standards de tests d'intégration

### Exigences de tests API

| Métrique | Cible | Tolérance | Red Flag |
|----------|-------|-----------|----------|
| **API Endpoint Coverage** | ≥ 90% | 80-89% | < 80% 🚨 |
| **Test Pass Rate** | 95-100% | 90-94% | < 90% 🚨 |
| **Test Flakiness** | < 2% | 2-5% | > 5% 🔥 |
| **P99 Response Time** | ≤ 500ms | 500-1000ms | > 1s 🐢 |
| **Suite Duration** | ≤ 5 min | 5-10 min | > 10 min ⏰ |
| **Integration Coverage** | 60-80% | 50-59% | < 50% ⚠️ |

### Couverture des tests API

- **Input Validation** : Scénarios typiques + edge cases + conditions limites testés
- **Response Validation** : Status codes + validation de schéma pour tous les endpoints
- **Authentication Coverage** : Tous les paths auth (login/refresh/expiry) + RBAC pour tous les endpoints

### Exigences de tests de base de données

- **Database Operations** : Toutes les opérations CRUD majeures testées avec connexions réelles à la base
- **Referential Integrity** : Contraintes et relations de base de données validées
- **Data Rollback** : 100% cleanup des tests avec rollback approprié en cas d'échec

### Exigences d'intégration de services

- **Service Communication** : Tous les appels de services downstream testés (avec mocking approprié)
- **Error Handling** : Scénarios de network failures, timeouts et downtime de services tiers
- **Performance** : P99 response time ≤ 500ms par endpoint (ajuster selon SLA)
- **Test Suite Duration** : ≤ 5 minutes pour la suite complète de tests d'intégration

---

## Standards de tests End-to-End (Playwright)

### Exigences du framework

| Métrique | Cible | Tolérance | Red Flag |
|----------|-------|-----------|----------|
| **Test Pass Rate** | ≥ 95% | 90-94% | < 90% 🚨 |
| **Flaky Test Rate** | ≤ 2% | 2-5% | > 5% 🔥 |
| **Avg Test Duration** | ≤ 30s par test | 30-120s | > 2 min 🐢 |
| **E2E Coverage** | ≥ 80% | 70-79% | < 70% ⚠️ |
| **Retry Usage** | < 5% | 5-10% | > 10% (instable) |

### Couverture et organisation

- **Test Coverage** : ≥ 80% line/branch coverage en combinant unit et E2E
- **Test Organization** : Tagging approprié avec `@smoke`, `@critical`, `@a11y`, `@regression`
- **User Journey Coverage** : Tous les flux utilisateur documentés doivent avoir des tests E2E correspondants

### Exigences techniques

- **Cross-browser Testing** : Tests exécutés sur Chromium, Firefox et WebKit
- **Performance Monitoring** : Track des temps de chargement de page, Core Web Vitals et requêtes réseau
- **Visual Regression** : Comparaisons de screenshots pour la cohérence UI
- **Accessibility** : Tests a11y automatisés avec intégration axe-playwright
- **Test Isolation** : Chaque test s'exécute dans un contexte navigateur isolé avec cleanup approprié

---

## Exigences d'environnement de test

### Standards d'infrastructure

- **Test Data** : Fixtures de test et seed data appropriés pour des tests cohérents
- **Environment Isolation** : Tests exécutés dans des environnements isolés sans affecter la production
- **CI/CD Integration** : Tous les tests doivent passer dans le pipeline d'intégration continue
- **Playwright Configuration** : playwright.config.js approprié avec browser matrix et retry logic
- **Test Reporting** : Résultats de tests clairs avec détails d'échec, rapports de couverture et rapports HTML Playwright
- **Parallel Execution** : Les tests peuvent s'exécuter en parallèle sans conflits

---

## Résumé des métriques de qualité

### Métriques de qualité du code

| Métrique | Bon seuil | Red Flag | Action requise |
|----------|-----------|----------|----------------|
| **Line Coverage** | 70-80% | < 50% | Augmenter la couverture |
| **Branch Coverage** | 80-90% | < 60% | Focus sur les classes logic-heavy |
| **Cyclomatic Complexity** | < 10 | > 15 | Refactorer les grandes méthodes |
| **CRAP Score** | < 15 (< 10 excellent) | > 30 | Refactoring immédiat requis |

### Métriques de qualité E2E (Playwright)

| Métrique | Cible | Tolérance | Red Flag |
|----------|-------|-----------|----------|
| **Test Pass Rate** | ≥ 95% | 90-94% | < 90% 🚨 |
| **Flaky Test Rate** | ≤ 2% | 2-5% | > 5% 🔥 |
| **Avg Test Duration** | ≤ 30s par test | 30-120s | > 2 min 🐢 |
| **E2E Coverage** | ≥ 80% | 70-79% | < 70% ⚠️ |
| **Retry Usage** | < 5% | 5-10% | > 10% (instable) |

### Métriques de qualité des tests d'intégration

| Métrique | Cible | Tolérance | Red Flag |
|----------|-------|-----------|----------|
| **API Endpoint Coverage** | ≥ 90% | 80-89% | < 80% 🚨 |
| **Test Pass Rate** | 95-100% | 90-94% | < 90% 🚨 |
| **Test Flakiness** | < 2% | 2-5% | > 5% 🔥 |
| **P99 Response Time** | ≤ 500ms | 500-1000ms | > 1s 🐢 |
| **Suite Duration** | ≤ 5 min | 5-10 min | > 10 min ⏰ |
| **Integration Coverage** | 60-80% | 50-59% | < 50% ⚠️ |
| **Retry Rate** | < 5% | 5-10% | > 10% (instable) |

---

## Principes clés de test

1. **Branch coverage élevée avec assertions significatives** > line coverage élevée avec tests faibles
2. **CRAP score** combine complexité et couverture pour identifier le code vraiment risqué
3. Les méthodes avec **Cyclomatic Complexity > 15** devraient être découpées en fonctions plus petites
4. **Focus des efforts de test** sur la logique métier critique et complexe plutôt que chercher 100% couverture
5. Les **tests flaky** indiquent des problèmes d'environnement ou des race conditions qui doivent être résolus
6. Les tests E2E devraient utiliser un **tagging approprié** (@smoke, @critical, @a11y, @regression) pour des tests ciblés
7. Les tests d'intégration doivent utiliser de **vraies bases de données/services**, pas des mocks, pour une vraie validation d'intégration
8. Les tests de **contract API** assurent une gestion appropriée des request/response et la conformité au schéma
9. Les **seuils de performance** doivent s'aligner avec les SLAs définis et les exigences d'expérience utilisateur

---

## Guidelines de communication

### NE JAMAIS affirmer la production-readiness sans :

- Confirmation explicite que TOUS les tests (unit/integration/e2e) passent
- Preuves des résultats d'exécution des tests
- Vérification de l'adéquation de la couverture de tests
- Confirmation que les métriques de qualité atteignent les seuils définis

### Au lieu de dire "production ready", utiliser un langage spécifique :

- "Prêt pour déploiement staging avec [caveats spécifiques]"
- "Nécessite [améliorations spécifiques] avant utilisation production"
- "Implémentation MVP - nécessite hardening [security/performance/testing]"
- "Fonctionnel mais nécessite [error handling/monitoring/etc.] production-grade"
- "Tests passants mais nécessite vérification [zone spécifique] avant production"

---

## Checklist d'implémentation

### Exigences de test pré-production

- [ ] Tous les tests unitaires passent avec 100% taux de réussite
- [ ] Tous les tests d'intégration passent avec 100% taux de réussite
- [ ] Tous les tests end-to-end passent avec 100% taux de réussite
- [ ] Résultats d'exécution des tests documentés et vérifiés
- [ ] Aucun test en échec dans le pipeline CI/CD

### Quality gates des tests unitaires

- [ ] Line coverage : 70-80% atteint pour la logique métier
- [ ] Branch coverage : 80-90% atteint pour les paths critiques
- [ ] Cyclomatic complexity : < 10 par fonction/méthode
- [ ] CRAP score : < 15 par méthode (< 10 préféré)
- [ ] Toutes les fonctions ont des tests pour happy path, conditions d'erreur, edge cases
- [ ] Dépendances externes correctement mockées
- [ ] Tests isolés et indépendants

### Validation des tests d'intégration

- [ ] API endpoint coverage : ≥ 90% des endpoints publics testés
- [ ] Toutes les opérations CRUD testées avec connexions réelles à la base
- [ ] Paths d'authentication et authorization testés
- [ ] Scénarios de gestion d'erreur testés (network failures, timeouts)
- [ ] P99 response time ≤ 500ms par endpoint
- [ ] Suite de tests d'intégration complète en ≤ 5 minutes
- [ ] Integration test coverage : 60-80% atteint

### Complétion des tests End-to-End (Playwright)

- [ ] Test pass rate : ≥ 95% pour releases stables (100% pour branches protégées)
- [ ] Flaky test rate : < 2%
- [ ] Durée moyenne des tests : ≤ 30 secondes par test
- [ ] Durée totale de la suite : ≤ 5-10 minutes
- [ ] Retry usage : < 5% des tests
- [ ] Cross-browser testing complété (Chromium, Firefox, WebKit)
- [ ] Tous les user journeys ont des tests E2E correspondants
- [ ] Tests correctement taggés (@smoke, @critical, @a11y, @regression)
- [ ] Visual regression testing complété
- [ ] Performance monitoring implémenté
- [ ] Accessibility testing avec axe-playwright complété

### Vérification de l'environnement de test

- [ ] Test data et fixtures correctement configurés
- [ ] Isolation de l'environnement vérifiée
- [ ] Playwright configuration (playwright.config.js) correctement mise en place
- [ ] Test reporting configuré (rapports HTML, rapports de couverture)
- [ ] Exécution parallèle fonctionnelle sans conflits

### Validation des métriques de qualité

- [ ] Toutes les métriques de qualité atteignent les seuils définis
- [ ] Aucun indicateur red flag présent
- [ ] Revues des quality gates complétées
- [ ] Rapports de couverture de tests générés et revus
- [ ] Benchmarks de performance documentés

### Documentation et communication

- [ ] Résultats de tests documentés avec preuves
- [ ] Limitations ou caveats des tests clairement énoncés
- [ ] Langage spécifique utilisé (pas d'affirmations "production ready" prématurées)
- [ ] Gaps de couverture de tests identifiés et documentés
- [ ] Prochaines étapes pour production-readiness clairement définies

---

## Stratégies de test par type de code

### Scripts et outils CLI

| Aspect | Approche |
|--------|----------|
| **Unit tests** | Tester les fonctions pures, parsing d'arguments, formatage de sortie |
| **Integration tests** | Tester l'exécution complète avec différents inputs |
| **Error handling** | Tester les codes de sortie, messages d'erreur |
| **Edge cases** | Fichiers manquants, permissions, inputs invalides |

### APIs et services web

| Aspect | Approche |
|--------|----------|
| **Unit tests** | Logique métier, validation, transformations |
| **Integration tests** | Endpoints avec vraie DB, auth, middleware |
| **E2E tests** | Flux utilisateur complets via HTTP |
| **Performance** | Load tests, stress tests, P99 latency |

### Bibliothèques et modules

| Aspect | Approche |
|--------|----------|
| **Unit tests** | API publique exhaustive, tous les edge cases |
| **Contract tests** | Vérifier que l'API ne casse pas |
| **Documentation tests** | Exemples de code qui compilent/s'exécutent |
| **Backwards compatibility** | Tests de régression pour breaking changes |

### Configuration et infrastructure

| Aspect | Approche |
|--------|----------|
| **Validation** | Syntaxe, schéma, valeurs valides |
| **Smoke tests** | Déploiement réussit, service démarre |
| **Integration** | Communication entre services |
| **Rollback tests** | Retour à version précédente fonctionne |

---

## Anti-patterns à éviter

| Anti-pattern | Problème | Solution |
|--------------|----------|----------|
| **Tests flaky** | Résultats non déterministes | Identifier et corriger les race conditions |
| **Tests couplés** | Un test dépend d'un autre | Isolation complète de chaque test |
| **Tests trop longs** | Suite lente, feedback tardif | Découper, paralléliser |
| **Coverage artificielle** | Code couvert mais non testé | Assertions significatives |
| **Mocking excessif** | Tests qui ne testent rien | Équilibre mocks/intégration |
| **Tests brittles** | Cassent au moindre changement | Tester le comportement, pas l'implémentation |
| **Ignorer les erreurs** | `catch (e) {}` dans les tests | Assertions sur les erreurs attendues |
