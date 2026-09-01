# -*- coding: utf-8 -*-
from odoo import api, fields, models


class FmaComplexiteRegle(models.Model):
    """Référentiel gammiste x typologie -> niveau de complexité.

    Reprend la matrice de l'onglet SEQUENCAGE du classeur, où chaque ligne
    portait une liste de typologies séparées par des « / ». Ici une ligne = un
    couple (gammiste, typologie), ce qui rend la table interrogeable.
    """

    _name = 'fma.complexite.regle'
    _description = "Règle de complexité par gammiste et typologie"
    _order = 'gammiste, typologie'
    _rec_name = 'libelle'

    gammiste = fields.Char(string="Gammiste", required=True, index=True)
    typologie = fields.Char(string="Typologie", required=True, index=True)
    niveau_id = fields.Many2one(
        'fma.complexite.niveau',
        string="Niveau de complexité",
        required=True,
        ondelete='restrict',
    )
    active = fields.Boolean(string="Actif", default=True)
    libelle = fields.Char(string="Libellé", compute='_compute_libelle', store=True)

    _gammiste_typologie_unique = models.Constraint(
        'UNIQUE(gammiste, typologie)',
        "Une règle existe déjà pour ce couple gammiste / typologie.",
    )

    @api.depends('gammiste', 'typologie', 'niveau_id.code')
    def _compute_libelle(self):
        for regle in self:
            regle.libelle = "%s / %s -> %s" % (
                regle.gammiste or '-',
                regle.typologie or '-',
                regle.niveau_id.code or '-',
            )

    @api.model
    def _niveau_pour(self, gammiste, typologie):
        """Retourne le niveau de complexité d'un couple, ou un recordset vide.

        Point d'entrée destiné à être appelé le jour où la typologie sera
        portée par un champ du produit ou du repère. Tant que ce n'est pas le
        cas, la complexité reste saisie sur l'OF et cette table sert de
        référentiel de saisie.
        """
        if not gammiste or not typologie:
            return self.env['fma.complexite.niveau']
        regle = self.search([
            ('gammiste', '=ilike', (gammiste or '').strip()),
            ('typologie', '=ilike', (typologie or '').strip()),
        ], limit=1)
        return regle.niveau_id
