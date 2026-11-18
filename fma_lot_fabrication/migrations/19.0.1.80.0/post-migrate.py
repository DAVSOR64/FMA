"""Passe les articles « Debit du lot » d'affaire en NON STOCKABLE.

Ces articles ne sont qu'une etiquette : Odoo exige qu'un ordre de
fabrication produise un article, une seance de debit n'en produit pas un
mais autant qu'il y a de reperes — ils sortent en sous-produits et
emportent la totalite du cout. Stockables, ils creaient une quantite
fantome valorisee a zero, que personne ne consomme jamais.

SEULS LES ARTICLES D'AFFAIRE SONT TOUCHES. L'article generique sert aussi
de repli a l'ensemble debite d'un lot saisi a la main — celui-la porte
l'en-cours et doit rester stockable. On le reconnait a sa reference en
« _DEB » et a son nom : l'ensemble debite d'un repere, lui, finit en
« -DEB » avec un tiret.

Chaque article est traite a part : Odoo refuse parfois de changer la
nature d'un article qui porte deja des mouvements, et un echec ne doit pas
arreter la mise a jour pour les autres.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api
    env = api.Environment(cr, SUPERUSER_ID, {})
    articles = env["product.product"].search([
        ("default_code", "=like", "%\\_DEB"),
        ("name", "=like", "Débit du lot — %"),
        ("is_storable", "=", True),
    ])
    faits, refuses = 0, []
    for article in articles:
        try:
            article.is_storable = False
            env.flush_all()
            faits += 1
        except Exception as erreur:  # noqa: BLE001
            env.invalidate_all()
            refuses.append("%s (%s)" % (article.default_code, erreur))
    _logger.info(
        "fma_lot_fabrication : %s article(s) de debit passes en non "
        "stockable, %s refuse(s)%s",
        faits, len(refuses), (" : " + " ; ".join(refuses)) if refuses else "")
