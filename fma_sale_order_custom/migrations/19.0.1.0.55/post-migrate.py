# -*- coding: utf-8 -*-
"""RAF HT : recalcul, et mesure de l'ecart avec l'ancienne valeur.

Le RAF etait porte par deux champs. x_studio_calcul_raf_ht, calcule mais non
stocke cote Studio, faisait une recherche sur account.move ;
x_studio_restant_a_facturer_ht_pivot, stocke, en gardait une photo qu'un
bouton rafraichissait. Les deux divergeaient des que personne n'appuyait.

Le champ stocke devient un calcul, avec une formule qui passe par
invoice_ids -- le lien que la commande porte elle-meme -- plutot que par une
recherche sur l'origine, un champ texte libre qu'une facture reprise d'un
autre systeme ne remplit pas toujours.

Cette reprise NE CORRIGE RIEN toute seule : Odoo recalcule le champ des que
la migration a tourne, puisqu'il devient calcule. Elle sert a MESURER ce que
ce changement deplace, avant que quiconque s'en apercoive sur un tableau de
bord. L'ecart est journalise commande par commande au-dela d'un euro.

Elle recense aussi ce qui cite encore le champ Studio. Il ne peut pas etre
supprime d'ici : une vue Studio qui le mentionnerait encore ferait echouer le
chargement. Le journal dit ou regarder avant de le retirer a la main.
"""
import logging

_logger = logging.getLogger(__name__)

#: Au-dela de cet ecart en euros, une commande est signalee nommement.
SEUIL = 1.0


def migrate(cr, version):
    cr.execute(
        """SELECT 1 FROM information_schema.columns
            WHERE table_name = 'sale_order'
              AND column_name = 'x_studio_restant_a_facturer_ht_pivot'"""
    )
    if not cr.fetchone():
        _logger.info("RAF HT : colonne absente, reprise sans objet")
        return

    # L'ancienne valeur, avant qu'Odoo ne recalcule.
    cr.execute(
        """SELECT id, name, x_studio_restant_a_facturer_ht_pivot
             FROM sale_order
            WHERE x_studio_restant_a_facturer_ht_pivot IS NOT NULL"""
    )
    anciennes = {ligne[0]: (ligne[1], ligne[2] or 0.0) for ligne in cr.fetchall()}
    _logger.info("RAF HT : %s commande(s) portaient une valeur", len(anciennes))

    # La table de liaison ligne de commande <-> ligne de facture porte le
    # rattachement. Sans elle, on ne mesure rien et on le dit.
    cr.execute(
        """SELECT 1 FROM information_schema.tables
            WHERE table_name = 'sale_order_line_invoice_rel'"""
    )
    if not cr.fetchone():
        _logger.warning(
            "RAF HT : table de liaison facture absente, ecart non mesure")
        return

    # La nouvelle valeur, selon la meme regle que le champ : total HT moins
    # les factures postees, avoirs deduits. Chaque facture ne compte QU'UNE
    # fois par commande, d'ou le DISTINCT : une facture porte plusieurs
    # lignes rattachees a la meme commande, et sommer les lignes multiplierait
    # son montant.
    cr.execute(
        """WITH liens AS (
               SELECT DISTINCT sol.order_id AS so_id, am.id AS move_id,
                      am.move_type, am.amount_untaxed
                 FROM sale_order_line_invoice_rel rel
                 JOIN sale_order_line sol ON sol.id = rel.order_line_id
                 JOIN account_move_line aml ON aml.id = rel.invoice_line_id
                 JOIN account_move am ON am.id = aml.move_id
                WHERE am.state = 'posted'
                  AND am.move_type IN ('out_invoice', 'out_refund')
           )
           SELECT so.id,
                  COALESCE(so.amount_untaxed, 0) - COALESCE((
                      SELECT SUM(CASE WHEN l.move_type = 'out_refund'
                                      THEN -l.amount_untaxed
                                      ELSE l.amount_untaxed END)
                        FROM liens l WHERE l.so_id = so.id), 0)
             FROM sale_order so
            WHERE so.id = ANY(%s)""",
        (list(anciennes) or [0],),
    )
    ecarts = []
    for so_id, nouvelle in cr.fetchall():
        nom, ancienne = anciennes.get(so_id, ("?", 0.0))
        if abs((nouvelle or 0.0) - ancienne) > SEUIL:
            ecarts.append((nom, ancienne, nouvelle or 0.0))

    if not ecarts:
        _logger.info("RAF HT : aucun ecart au-dela de %s EUR", SEUIL)
    else:
        _logger.warning(
            "RAF HT : %s commande(s) changent de valeur de plus de %s EUR",
            len(ecarts), SEUIL)
        for nom, ancienne, nouvelle in sorted(
                ecarts, key=lambda e: abs(e[2] - e[1]), reverse=True)[:30]:
            _logger.warning(
                "  %-18s ancien %12.2f  nouveau %12.2f  ecart %12.2f",
                nom, ancienne, nouvelle, nouvelle - ancienne)

    # Ce qui cite encore le champ Studio : a nettoyer a la main avant de le
    # supprimer, sinon le chargement de la vue echouera.
    cr.execute(
        """SELECT 'vue', v.id, COALESCE(v.name->>'fr_FR', v.name->>'en_US')
             FROM ir_ui_view v
            WHERE v.arch_db::text LIKE '%%x_studio_calcul_raf_ht%%'"""
    )
    citations = cr.fetchall()
    if citations:
        _logger.warning(
            "x_studio_calcul_raf_ht est encore cite par %s vue(s) :",
            len(citations))
        for _kind, vid, nom in citations[:20]:
            _logger.warning("  vue %s : %s", vid, nom)
    else:
        _logger.info(
            "x_studio_calcul_raf_ht n'est plus cite par aucune vue : il peut "
            "etre supprime depuis Studio")
