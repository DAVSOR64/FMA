# -*- coding: utf-8 -*-
from odoo import Command, fields, models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    atelier_id = fields.Many2one(
        "fma.atelier",
        string="Atelier (FMA)",
        index=True,
        tracking=True,
        copy=True,
        help=(
            "Atelier métier sur lequel l'OF sera produit. "
            "Ce champ sert au macro-planning et aux restitutions de capacité, "
            "sans créer d'entrepôts ou de transferts logistiques entre ateliers."
        ),
    )

    def _link_workorders_and_moves(self):
        """Ne chaine pas les operations les unes derriere les autres.

        Odoo 19 pose un lien « Bloque par » entre chaque operation et la
        precedente, **meme quand les dependances sont desactivees** : le
        reglage « Dependances des ordres de travail » ne fait que choisir
        entre un graphe defini sur la nomenclature et une chaine lineaire
        imposee (voir la branche ``else`` de la methode d'origine).

        Chez FMA, une operation doit pouvoir demarrer sans attendre que la
        precedente soit finie : l'usinage d'une serie commence pendant que le
        banc CU termine la sienne. On laisse donc Odoo faire son travail — le
        rattachement des mouvements de composants aux operations, qui est
        l'autre moitie de cette methode et qui, lui, est indispensable — puis
        on retire la chaine.

        Une nomenclature qui declare explicitement ses dependances garde les
        siennes : on ne touche qu'a la chaine automatique.
        """
        res = super()._link_workorders_and_moves()
        if self.workorder_ids and not self.allow_workorder_dependencies:
            self.workorder_ids.blocked_by_workorder_ids = [Command.clear()]
        return res
