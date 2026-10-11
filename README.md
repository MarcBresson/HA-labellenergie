<p align="center"><img src="assets/logo-entier.svg" alt="La Belle Énergie" width="360"></p>

# La Belle Énergie pour Home Assistant

Intégration Home Assistant (installable via [HACS](https://hacs.xyz)) qui récupère depuis votre espace client [La Belle Énergie](https://espace-client.labellenergie.fr) les tarifs de votre contrat d'électricité : abonnement, prix du kWh, heures creuses, puissance souscrite… et le **prix du kWh en vigueur à cet instant**, utilisable directement dans le tableau de bord **Énergie**.

> ⚠️ **Intégration non officielle.** Elle n'est ni éditée ni soutenue par La Belle Énergie. Elle s'appuie sur l'API de l'espace client, qui n'est pas documentée publiquement et peut changer sans préavis.

## Ce que fournit l'intégration

Un **appareil** est créé pour chaque point de livraison (PDL) de votre compte, nommé :

```
labelleenergie - {numéro et rue}
```

Exemple : `labelleenergie - 4 bd DE CRETEIL`

Chaque appareil expose les entités suivantes. Toutes sont rangées dans la section **Diagnostic** de l'appareil, sauf **Prix actuel du kWh**, **Heure creuse en cours**, **Calendrier des heures creuses** et les entités de facturation :

| Entité | Unité | Description |
|---|---|---|
| Abonnement mensuel TTC | €/mois | Prix de l'abonnement TTC |
| Prix du kWh heures creuses TTC | €/kWh | Indisponible pour une offre Base |
| Prix du kWh heures pleines TTC | €/kWh | Indisponible pour une offre Base |
| Prix du kWh base TTC | €/kWh | Indisponible pour une offre Heures pleines / Heures creuses |
| Plages d'heures creuses | texte | Ex. `1h04 - 7h04, 14h34 - 16h34` (liste dans l'attribut `plages`) |
| Puissance souscrite | kVA | |
| Dernière modification de l'offre | date | Date du dernier changement de tarif |
| Numéro de point de livraison | texte | Numéro du PDL |
| Adresse | texte | `{complément} {numéro et rue}, {code postal} {ville}` |
| **Prix actuel du kWh** | €/kWh | Prix en vigueur à l'instant présent (voir ci-dessous) |
| **Heure creuse en cours** | marche / arrêt | Actif pendant les heures creuses (capteur binaire), pratique pour les automatisations. Indisponible pour une offre Base |
| **Calendrier des heures creuses** | calendrier | Un événement « Heures creuses » par plage horaire, chaque jour. Actif pendant les heures creuses. Indisponible pour une offre Base |
| **Facture mensuelle TTC** | € | Montant TTC de la dernière facture (attributs `mois` et `total_ht`) |
| **Total payé TTC (cumul)** | € | Somme de toutes les factures depuis la première |
| **Total année passée TTC** | € | Somme des factures de l'année civile précédente |
| **Total année en cours TTC** | € | Somme des factures de l'année civile en cours |
| **Total 12 derniers mois TTC** | € | Somme des 12 mois se terminant au dernier mois facturé (attributs `mois_debut` et `mois_fin`) |

Une entité dont la valeur n'existe pas dans votre offre (par exemple le prix heures creuses d'une offre Base) apparaît comme « indisponible » : c'est normal.

### Prix actuel du kWh

- Offre **Base** : c'est le prix de base.
- Offre **Heures pleines / Heures creuses** : c'est le prix heures creuses si l'heure actuelle (heure de Paris) est dans l'une des plages d'heures creuses, le prix heures pleines sinon.

Le capteur expose aussi les attributs `heure_creuse` (`true` / `false`, absent pour une offre Base) et `option` (`base` ou `hp_hc`).

Il n'est **pas** interrogé en boucle : l'intégration connaît les horaires de bascule et ne met à jour le capteur (comme le capteur binaire et le calendrier) qu'à chaque passage heures creuses ↔ heures pleines (par exemple à 1h04, 7h04, 14h34 et 16h34 pour les plages ci-dessus).

## Installation

### Avec HACS (recommandé)

1. Dans Home Assistant, ouvrez **HACS**.
2. Menu **⋮** (en haut à droite) → **Dépôts personnalisés**.
3. Saisissez l'URL de ce dépôt GitHub, choisissez la catégorie **Intégration**, puis **Ajouter**.
4. Recherchez **La Belle Énergie** dans HACS, puis **Télécharger**.
5. **Redémarrez** Home Assistant.

### Manuellement

Copiez le dossier `custom_components/labellenergie` dans le dossier `custom_components` de votre configuration Home Assistant, puis redémarrez.

## Connexion

1. **Paramètres → Appareils et services → Ajouter une intégration**.
2. Recherchez **La Belle Énergie**.
3. Saisissez l'**adresse e-mail** et le **mot de passe** que vous utilisez sur [espace-client.labellenergie.fr](https://espace-client.labellenergie.fr).

L'intégration vérifie la connexion, puis crée automatiquement un appareil par point de livraison présent sur votre compte.

- Si vous avez plusieurs comptes La Belle Énergie, ajoutez l'intégration une fois par compte.
- Si votre mot de passe change, Home Assistant vous propose de le ressaisir (notification de reconnexion).
- Si un nouveau point de livraison apparaît sur votre compte, ses entités sont ajoutées automatiquement et une **notification** vous en informe.

## Utilisation dans le tableau de bord Énergie

L'intégration fournit les **prix**. Pour que le tableau de bord Énergie calcule un coût, il faut aussi une source de **consommation** en kWh (par exemple via votre compteur Linky : intégration Linky/Enedis, passerelle Linky-Teleinfo, ESPHome, etc.).

1. **Paramètres → Tableaux de bord → Énergie**.
2. Dans **Consommation du réseau électrique**, ajoutez (ou modifiez) votre source de consommation en kWh.
3. Pour le suivi des coûts, choisissez **Utiliser une entité avec le prix actuel**.
4. Sélectionnez l'entité **Prix actuel du kWh** de votre point de livraison.
5. Enregistrez.

Home Assistant multiplie alors chaque consommation par le prix en vigueur au moment où elle a lieu : le passage heures creuses / heures pleines est donc pris en compte automatiquement.

Remarques :

- Le tableau de bord Énergie n'accepte que les entités dont l'unité est la devise de votre installation suivie de `/kWh` (ici `EUR/kWh`). Vérifiez que la devise est bien l'euro dans **Paramètres → Système → Général**.
- Le prix de l'**abonnement** n'est pas pris en compte par le tableau de bord Énergie. Si vous souhaitez l'inclure, utilisez l'entité *Abonnement mensuel TTC* dans vos propres tableaux de bord ou automatisations.

## Factures et historique

Les montants proviennent de l'historique de facturation de l'espace client (`total_ttc` de chaque mois).

- **Backfill** : à la première création des capteurs *Facture mensuelle TTC* et *Total payé TTC (cumul)*, tout l'historique est importé dans les **statistiques de long terme** de l'entité (un point par mois), pour que les graphiques d'historique et de statistiques remontent jusqu'à votre première facture. Cet import n'est fait **qu'une fois** par entité ; ensuite l'enregistreur de Home Assistant suit l'évolution de l'état. Si vous supprimez les statistiques de l'entité, rechargez l'intégration pour relancer l'import.
- Les factures ne donnent pas leur date d'émission : chaque mois est daté du **1er du mois à 00h00 (heure de Paris)**.
- *Facture mensuelle TTC* est un compteur remis à zéro chaque mois (`last_reset`), et *Total payé TTC (cumul)* un total qui ne fait que croître : tous deux utilisent la classe d'état `total`. Les trois totaux annuels n'enregistrent pas de statistiques.
- Les années civiles sont celles de l'heure de Paris ; le passage au 1er janvier n'est pris en compte qu'à la mise à jour suivante (24 h au plus).
- La facturation est rattachée à un **groupe de facturation**, pas à un PDL : si plusieurs PDL de votre compte en partagent un, chacun affichera le même montant.
- L'intégration dépend du composant `recorder` (activé par défaut dans Home Assistant).

## Fréquence de mise à jour

- Les tarifs (abonnement, prix, plages, puissance) et les factures sont relus **une fois par 24 heures**, ainsi qu'au démarrage de Home Assistant.
- Le **prix actuel du kWh** est recalculé localement à chaque bascule heures creuses / heures pleines, sans appel réseau.

## Confidentialité

- Vos identifiants sont enregistrés dans la configuration de Home Assistant (dossier `.storage`), **en clair**, comme pour la plupart des intégrations. Protégez l'accès à votre installation et à vos sauvegardes.
- Ils ne sont envoyés qu'à `espace-client.labellenergie.fr`.

## Dépannage

| Problème | Piste |
|---|---|
| « E-mail ou mot de passe incorrect » | Vérifiez que vous parvenez à vous connecter sur le site de l'espace client avec les mêmes identifiants. |
| « Impossible de joindre l'espace client » | Problème réseau ou indisponibilité du site ; réessayez plus tard. |
| Les entités sont « indisponibles » | Normal si la valeur n'existe pas dans votre offre. Sinon, consultez les journaux. |
| Plus aucune mise à jour | Le site a peut-être changé son API : consultez les journaux et ouvrez un ticket. |

Pour activer les journaux détaillés, ajoutez à `configuration.yaml` :

```yaml
logger:
  logs:
    custom_components.labellenergie: debug
```

## Développement

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
pytest
```
