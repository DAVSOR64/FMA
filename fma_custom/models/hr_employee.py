# -*- coding: utf-8 -*-
"""Réparation des avatars hérités d'une duplication de fiche employé.

Odoo n'affiche des initiales que lorsque la fiche ne porte AUCUNE photo :
`image_1920` vide, l'avatar est alors généré à la volée. Dupliquer une fiche
recopie ce champ. Les employés créés par duplication héritent donc de l'image
de l'original — la même lettre pour tout le monde, partout où l'avatar est
affiché : ressources humaines, discussion, écran atelier.

Vider `image_1920` sur ces fiches suffit à rendre à chacune son avatar propre.
"""
import hashlib
import logging

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def _fma_avatars_partages(self):
        """Regroupe les fiches qui portent EXACTEMENT la même image.

        Le critère est volontairement strict : une photo prise pour une
        personne n'est jamais partagée par une autre. Deux fiches portant le
        même octet pour octet ne peuvent venir que d'une duplication. On ne
        risque donc pas d'effacer une vraie photo.
        """
        par_empreinte = {}
        for employe in self:
            image = employe.image_1920
            if not image:
                continue
            empreinte = hashlib.sha256(
                image if isinstance(image, bytes) else image.encode()
            ).hexdigest()
            par_empreinte.setdefault(empreinte, self.browse())
            par_empreinte[empreinte] |= employe
        return {e: f for e, f in par_empreinte.items() if len(f) > 1}

    def action_fma_diagnostiquer_avatars(self):
        """Compte, sans rien modifier, les fiches concernées."""
        partages = self._fma_avatars_partages()
        if not partages:
            raise UserError(_(
                "Aucune image partagée parmi les %s fiches sélectionnées.\n\n"
                "Les avatars identiques ne viennent donc pas d'une "
                "duplication.", len(self)
            ))
        lignes = []
        for fiches in partages.values():
            lignes.append("• %s fiches : %s" % (
                len(fiches), ", ".join(fiches.mapped("name")[:6])
                + (" …" if len(fiches) > 6 else "")
            ))
        raise UserError(_(
            "%s image(s) partagée(s) par plusieurs fiches, soit %s employés "
            "au total :\n\n%s\n\nUtilisez « Rendre son avatar à chaque "
            "employé » pour les vider. Les photos individuelles ne sont pas "
            "touchées.",
            len(partages),
            sum(len(f) for f in partages.values()),
            "\n".join(lignes),
        ))

    def action_fma_reinitialiser_avatars(self):
        """Vide l'image des fiches qui la partagent avec d'autres."""
        partages = self._fma_avatars_partages()
        concernes = self.browse()
        for fiches in partages.values():
            concernes |= fiches
        if not concernes:
            raise UserError(_(
                "Aucune image partagée : rien à réinitialiser."
            ))
        concernes.write({"image_1920": False})
        _logger.info(
            "FMA : avatar réinitialisé sur %s fiche(s) employé.", len(concernes)
        )
        raise UserError(_(
            "Avatar réinitialisé sur %s fiche(s).\n\n"
            "Chacune retrouve l'avatar que Odoo génère pour elle. Une photo "
            "peut être reposée normalement sur les fiches concernées.",
            len(concernes),
        ))
