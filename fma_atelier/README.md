# FMA Atelier

Module socle Odoo pour ajouter une notion métier d'atelier sans créer d'entrepôts supplémentaires.

## Contenu

- Modèle `fma.atelier`
- Menu Fabrication > Configuration > Ateliers
- Champ `atelier_id` sur les ordres de fabrication `mrp.production`
- Filtres et regroupements par atelier sur les OF
- Données de départ : Atelier ALU et Atelier BOIS

## Installation conseillée

1. Copier le dossier `fma_atelier` dans les addons personnalisés.
2. Redémarrer Odoo.
3. Mettre à jour la liste des applications.
4. Installer le module `FMA Atelier`.
5. Ensuite seulement, modifier les modules macro-planning/capacité pour dépendre de `fma_atelier`.

## Dépendance à ajouter ensuite dans les autres modules

Dans les `__manifest__.py` des modules qui utilisent `atelier_id` :

```python
"depends": [
    ...,
    "fma_atelier",
],
```

## Logique métier

- La charge vient de `mrp.production.atelier_id`.
- La capacité pourra ensuite être ventilée par atelier dans le module capacité.
- Aucun entrepôt, emplacement ou transit inter-atelier n'est créé.
