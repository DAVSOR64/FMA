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

    def _fma_notifier(self, titre, message, danger=False):
        """Affiche un resultat SANS annuler la transaction.

        Lever une UserError afficherait bien le message, mais provoquerait un
        rollback : l'ecriture qui precede serait defaite. C'est ce qui rendait
        la reinitialisation sans effet — le message s'affichait, rien ne
        changeait.
        """
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": titre,
                "message": message,
                "type": "danger" if danger else "success",
                "sticky": True,
            },
        }

    def action_fma_diagnostiquer_avatars(self):
        """Compte, sans rien modifier, les fiches concernees."""
        partages = self._fma_avatars_partages()
        if not partages:
            return self._fma_notifier(
                _("Aucune image partagée"),
                _("Les %s fiches sélectionnées portent chacune une image qui "
                  "leur est propre, ou aucune image.", len(self)),
            )
        lignes = []
        for fiches in partages.values():
            noms = fiches.mapped("name")
            lignes.append("• %s fiches : %s%s" % (
                len(fiches), ", ".join(noms[:6]), " …" if len(noms) > 6 else ""
            ))
        return self._fma_notifier(
            _("%s image(s) partagée(s)", len(partages)),
            _("%s employés concernés :\n%s\n\nUtilisez « Rendre son avatar à "
              "chaque employé » pour les vider. Les photos individuelles ne "
              "sont pas touchées.",
              sum(len(f) for f in partages.values()), "\n".join(lignes)),
        )

    def action_fma_reinitialiser_avatars(self):
        """Vide l'image des fiches qui la partagent avec d'autres."""
        partages = self._fma_avatars_partages()
        concernes = self.browse()
        for fiches in partages.values():
            concernes |= fiches
        if not concernes:
            return self._fma_notifier(
                _("Rien à réinitialiser"),
                _("Aucune image n'est partagée par plusieurs fiches."),
            )
        concernes.write({"image_1920": False})
        _logger.info(
            "FMA : avatar réinitialisé sur %s fiche(s) employé.", len(concernes)
        )
        return self._fma_notifier(
            _("Avatar réinitialisé sur %s fiche(s)", len(concernes)),
            _("Chacune retrouve l'avatar généré pour elle. Une photo peut être "
              "reposée normalement sur les fiches concernées."),
        )
