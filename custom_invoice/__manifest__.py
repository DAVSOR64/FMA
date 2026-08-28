# -*- coding: utf-8 -*-
{
    "name": "Custom Invoice Text Block",
    # 1.0.2 : la facture imprimee affiche commercial_id, avec repli sur
    # l'ancienne selection pour les factures anterieures a la bascule.
    # 1.0.3 : xpath du bloc affacturage reancre sur #payment_term, dont la
    # classe a change en v19 et qui desactivait toute la vue heritee.
    # 1.0.4 : reactive les deux vues du module, eteintes par la migration et
    # qu'une mise a jour de module ne rallume pas d'elle-meme.
    # 1.0.5 : priority 99, pour s'appliquer apres l10n_fr_account (v19) au lieu
    # de le casser.
    # 1.0.6 : priority forcee par le record, dans la meme ecriture que active.
    # 1.0.7 : le gabarit masque les blocs standard au lieu de les supprimer,
    # pour ne plus casser les ancrages des autres vues heritees du rapport.
    # 1.0.8 : partner.siret -> partner.commercial_partner_id.company_registry,
    # le champ de l10n_fr n'existe plus en v19.
    "version": "19.0.1.0.8",
    "summary": "Show text block on invoice based on contact boolean field",
    "author": "Your Name",
    "depends": ["account", "custom"],
    "data": [
        "views/report_invoice.xml",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
