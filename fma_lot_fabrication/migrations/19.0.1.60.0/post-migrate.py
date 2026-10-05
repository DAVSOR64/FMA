# -*- coding: utf-8 -*-
"""« Debit du lot » : l'article de l'OF de debit n'est plus suivi en stock.

L'OF de debit porte desormais l'article generique du lot, pour le nombre de
menuiseries, et sort les ensembles debites en sous-produits. L'article
generique n'est qu'une etiquette : suivi en stock, il s'y accumulerait de la
taille du lot a chaque debit, sans que rien ne le consomme jamais.

La fiche est en noupdate — une mise a jour ne la retouche pas. On la passe
donc ici en non suivi, et on la renomme si personne ne l'a fait.

Sont concernes : la fiche livree par le module, et l'article debite par
defaut de chaque societe. Un article qui est l'ensemble debite d'une
menuiserie est laisse tel quel, meme designe par erreur comme article par
defaut : celui-la doit rester en stock.

Rejouable : un article deja non suivi est passe. Rien ne bloque la mise a
jour — un refus d'Odoo est trace, et l'article reste a reprendre a la main.

Les ordres de debit deja generes ne sont pas touches.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

ANCIEN_NOM = "Ensemble debite - lot"
NOUVEAU_NOM = "Débit du lot"


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Product = env["product.product"].with_context(active_test=False)

    articles = Product.browse()
    defaut = env.ref(
        "fma_lot_fabrication.product_ensemble_debite", raise_if_not_found=False)
    if defaut:
        articles |= defaut
    if "fma_lot_product_debit_id" in env["res.company"]._fields:
        articles |= env["res.company"].with_context(
            active_test=False).search([]).fma_lot_product_debit_id
    if not articles:
        _logger.info("Debit du lot : aucun article generique, rien a reprendre")
        return

    # L'ensemble debite d'une menuiserie n'est pas un article generique.
    reperes = env["fma.lot.fabrication.line"].search(
        [("product_debit_id", "in", articles.ids)]).product_debit_id
    for article in articles:
        if article in reperes or article.fma_semi_fini == "debit":
            _logger.warning(
                "Debit du lot : %s est l'ensemble debite d'une menuiserie, "
                "il reste suivi en stock. Il ne peut pas servir d'article "
                "debite par defaut.", article.display_name)
            continue

        if defaut and article == defaut:
            _renommer(env, article)

        if not article.is_storable:
            _logger.info(
                "Debit du lot : %s deja non suivi en stock",
                article.display_name)
            continue

        en_stock = sum(env["stock.quant"].sudo().search([
            ("product_id", "=", article.id),
            ("location_id.usage", "=", "internal"),
        ]).mapped("quantity"))
        en_cours = env["stock.move"].sudo().search_count([
            ("product_id", "=", article.id),
            ("state", "not in", ("done", "cancel", "draft")),
        ])
        try:
            with cr.savepoint():
                article.product_tmpl_id.write({"is_storable": False})
        except Exception:  # noqa: BLE001 — trace, la mise a jour continue
            _logger.exception(
                "Debit du lot : %s n'a pas pu passer en non suivi. A faire a "
                "la main : decocher « Suivre l'inventaire » sur sa fiche.",
                article.display_name)
            continue
        _logger.info(
            "Debit du lot : %s n'est plus suivi en stock", article.display_name)
        if en_stock or en_cours:
            _logger.warning(
                "Debit du lot : %s portait %s unite(s) en stock et %s "
                "mouvement(s) en cours, issus des lots anterieurs. Ils ne "
                "sont pas repris : les quantites ne s'affichent plus, les "
                "ordres en cours se terminent normalement.",
                article.display_name, en_stock, en_cours)


def _renommer(env, article):
    """« Ensemble debite - lot » -> « Débit du lot », si le nom est d'origine."""
    langues = [code for code, _nom in env["res.lang"].get_installed()]
    for langue in langues:
        modele = article.product_tmpl_id.with_context(lang=langue)
        if (modele.name or "").strip() == ANCIEN_NOM:
            modele.name = NOUVEAU_NOM
            _logger.info(
                "Debit du lot : %s renomme « %s » (%s)",
                article.default_code or article.id, NOUVEAU_NOM, langue)
