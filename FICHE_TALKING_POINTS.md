# 🎤 FICHE TALKING POINTS — Soutenance

> À garder sous les yeux. Chiffres clés + réponses aux questions pièges.

---

## 📊 CHIFFRES À RETENIR PAR CŒUR

| Métrique | Valeur |
|----------|--------|
| Inscriptions planifiées | **1852/1852 (100 %)** |
| Étudiants uniques couverts | **475/475 (100 %)** |
| Groupes formés | **145** |
| Sessions de lab | **599** (295 S1 + 304 S2) |
| Statut solveur | **OPTIMAL** (2 runs, 0 INFEASIBLE) |
| Temps de calcul total | **6.68 s** (3.73 s S1 + 2.95 s S2) |
| Conflits C1 / C4 / C7 | **0 / 0 / 0** |
| Écart-type tailles groupes | **2.37** (cible 12) |
| Tests automatisés | **267 tests passent** |

---

## 🎯 PHRASE D'ACCROCHE (thèse centrale)

> « Un statut OPTIMAL du solveur ne garantit PAS la conformité métier.
> Ma contribution : un système qui garantit la conformité, pas seulement l'optimalité mathématique. »

---

## 🏗️ DÉCRIRE L'ARCHITECTURE EN 20 SECONDES

> « C'est une **co-optimisation itérative** : une phase heuristique informée par les
> contraintes forme les groupes en 8 phases de recovery avec feedback, puis un solveur
> CP-SAT place les sessions de façon optimale. Résultat : 100 % de couverture, 0 conflit,
> en moins de 7 secondes. »

Les 4 étages : **Validation préventive → Formation (8 phases) → CP-SAT → Audit métier**

---

## 🥊 DÉFENSE DU CHOIX : Heuristique + CP-SAT vs Co-opt pure

**Ce que je gagne (5) :** temps borné (7s) · complétude garantie (100 %) · explicabilité · maintenabilité · faible coût dev

**Ce que je sacrifie (3) :** optimum mathématique du groupement · décisions simultanées · garantie meilleure solution

**Argument massue :**
> « Je sacrifie 3 garanties *théoriques* pour gagner 5 avantages *pratiques*.
> Je préfère une solution 100 % conforme, explicable et calculée en 7 s,
> plutôt qu'un optimum théorique fragile, opaque et potentiellement incalculable
> en temps réel. »

**Analogie :**
> « C'est le GPS qui trouve un itinéraire à 3 % près en 2 secondes, versus celui qui
> trouve l'itinéraire parfait en 2 heures. Pour un usage réel, le premier gagne toujours. »

---

## ⚠️ QUESTIONS PIÈGES & RÉPONSES

### Q1 — « Peut-on utiliser l'outil directement pour l'année 2026-2027 ? »
> **« Oui, mais pas en un clic. »** Le cœur algorithmique est générique et réutilisable
> tel quel. Ce qui demande une intervention :
> 1. **Fournir les données 2026-2027** au format attendu (`master_schedule.csv`)
> 2. **Mettre à jour le calendrier** dans `user_config.json` (semaines S1/S2, semaine de début)
> 3. **Vérifier les paramètres calibrés** sur 2025-2026 (salles, override Física max=15)
> 4. **Re-valider** le résultat via l'audit métier (jamais de confiance aveugle)
>
> « Ce n'est pas un outil presse-bouton clé-en-main, mais un système opérationnel avec
> une phase de préparation de données de quelques heures, suivie d'une re-validation. »

### Q2 — « Pourquoi pas une co-optimisation unifiée ? »
> « J'ai implémenté une co-optimisation *itérative* avec feedback. L'approche unifiée
> gagnerait 5-10 % de qualité théorique, mais avec un temps de calcul incertain
> (minutes-heures) et une implémentation 2-3× plus complexe. Sur mes données réelles :
> 100 % placement, 0 conflit en 6.68 s. L'optimum ne peut pas mieux faire sur le placement. »

### Q3 — « Comment savez-vous que vous êtes proche de l'optimum sans le calculer ? »
> « Je ne prétends pas mesurer un écart exact — ce serait malhonnête. Mon indicateur est
> *métier*, pas mathématique : 100 % placement, 0 conflit, écart-type 2.37, placement CP-SAT
> OPTIMAL sur les 2 semestres. L'écart à un optimum global hypothétique est une question
> académique sans impact opérationnel. »

### Q4 — « Les groupes peuvent-ils changer ? »
> « Oui, via les 8 phases de recovery. Exemple : S1_Física démarre à 14 groupes, détecte
> 9 étudiants sans créneau, crée automatiquement un groupe overflow → 15 groupes, 214/214.
> C'est un feedback actif entre placement et groupement. »

### Q5 — « Les OVERFLOW, ce sont des exceptions/bugs ? »
> « Non, c'est une stratégie intentionnelle. Quand les créneaux préférés sont saturés,
> le système crée des groupes overflow dans des créneaux alternatifs conformes.
> 18 overflow sur 145 groupes = preuve que le système s'adapte au lieu de déclarer INFEASIBLE. »

### Q6 — « Pourquoi certains fichiers CSV de l'ancienne version ont disparu ? »
> « Ils représentaient des états intermédiaires de calcul. Je les ai consolidés dans une
> architecture plus robuste : config centralisée, calculs en mémoire, outputs concentrés
> sur les livrables métier. Moins de fichiers = moins de désynchronisation. Le rapport
> pipeline documente chaque étape avec plus de détail que les anciens CSV. »

### Q7 — « Votre système a-t-il des limites ? »
> « Oui, assumées : pas de garantie d'optimum mathématique sur le groupement, et des
> heuristiques calibrées pour Loyola. C'est pourquoi j'ai développé l'audit métier qui
> détecte toute anomalie a posteriori avec remèdes quantifiés. La note technique chiffre
> précisément quand une refonte (Option A/B) se justifierait. »

---

## 🔭 PERSPECTIVES (clore sur du positif)

| Option | Description | Coût | Quand |
|--------|-------------|------|-------|
| **Actuel** | 8 phases + audit | ✅ Déployé | Maintenant |
| **A** | Automatiser overrides manuels | 12-25 k€ | Si > 10 h/sem manuel |
| **B** | Co-optimisation unifiée | 50-95 k€ | Multi-départements |

> « Le système actuel couvre 95-100 % des besoins. La note technique fournit une feuille
> de route chiffrée pour les évolutions futures. »

---

## ✅ PHRASE DE CLÔTURE

> « J'ai livré un système opérationnel, validé sur données réelles, qui garantit 100 %
> de couverture et 0 conflit en 7 secondes, tout en garantissant la conformité métier —
> ce qu'un simple statut OPTIMAL ne fait pas. Et j'ai documenté une feuille de route
> chiffrée pour son évolution. »
