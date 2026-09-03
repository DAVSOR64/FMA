# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

from .constants import FMA_CATEGORIES_APPRO

_logger = logging.getLogger(__name__)


class PurchaseOrderLine(models.Model):
    """Famille d'approvisionnement au niveau de la ligne d'achat.

    Porter la famille ici, plutôt que de la recalculer à chaque lecture depuis
    le produit, sert deux usages : la ventilation sur l'OF, et l'écran de
    détail où l'on veut grouper les lignes par famille pour comprendre d'où
    sort la date affichée.
    """

    _inherit = 'purchase.order.line'

    fma_famille_appro = fields.Selection(
        FMA_CATEGORIES_APPRO,
        string="Famille d'approvisionnement (FMA)",
        compute='_compute_fma_famille_appro', store=True, index=True,
        help="Déduite de la catégorie du produit, ou de sa sous-famille et de "
             "sa famille si elles sont renseignées. Le complémentaire est la "
             "valeur par défaut.",
    )

    @api.depends(
        'product_id',
        'product_id.product_tmpl_id.categ_id.fma_famille_appro',
        'product_id.product_tmpl_id.family_id.fma_famille_appro',
        'product_id.product_tmpl_id.subfamily_id.fma_famille_appro',
    )
    def _compute_fma_famille_appro(self):
        for ligne in self:
            if ligne.display_type or not ligne.product_id:
                ligne.fma_famille_appro = False
                continue
            # Le complémentaire est la famille par défaut : rien de ce qui est
            # commandé pour l'affaire ne doit passer à la trappe.
            ligne.fma_famille_appro = (
                ligne.product_id.product_tmpl_id._fma_famille_appro()
                or 'complementaire'
            )

    @api.model
    def _fma_recalculer_familles(self):
        """Reclasse les lignes d'achat encore vivantes.

        Appelé quand la famille d'approvisionnement d'une catégorie, d'une
        famille ou d'une sous-famille change : aucun chemin d'@api.depends ne
        remonte jusqu'ici lorsque la valeur est portée par une catégorie
        parente. On se limite aux commandes encore en cours, l'historique
        n'ayant pas d'intérêt pour l'ordonnancement.
        """
        try:
            lignes = self.search([('state', 'not in', ('cancel', 'done'))])
            if not lignes:
                return
            champ = self._fields['fma_famille_appro']
            self.env.add_to_compute(champ, lignes)
            lignes.flush_recordset()
        except Exception:
            _logger.exception(
                "Ordonnancement FMA : reclassement des lignes d'achat ignoré."
            )

    def write(self, vals):
        result = super().write(vals)
        # La date d'arrivée prévue est portée par la ligne : c'est elle qui
        # alimente les colonnes « Arrivée … » de l'OF.
        if {'date_planned', 'product_qty', 'product_id'} & set(vals):
            self.order_id._fma_invalider_appro()
        return result

    def action_fma_ouvrir_commande(self):
        """Ouvre la commande d'achat portant cette ligne.

        L'ecran de detail liste des LIGNES, pas des commandes : c'est au
        niveau de la ligne que se lisent la famille et la date qui remonte sur
        l'OF. Mais la question qui suit la lecture est presque toujours « et
        cette commande, ou en est-elle ? », et il fallait jusqu'ici la
        rechercher a la main dans les achats.

        Une action et non un simple clic sur la ligne : la liste porte des
        lignes d'achat, un clic y ouvrirait la fiche de la ligne, pas celle de
        la commande.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.order_id.name or "Commande d'achat",
            'res_model': 'purchase.order',
            'res_id': self.order_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            # En fenetre et non en pleine page : on revient au detail des
            # approvisionnements en fermant, sans perdre le filtre ni le
            # regroupement en cours.
            'target': 'new',
        }
