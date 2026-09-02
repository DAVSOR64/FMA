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
        """Etat brut des images des fiches selectionnees.

        La premiere version ne signalait que les images strictement identiques.
        Elle ne voyait donc rien la ou le probleme existe pourtant : une
        duplication peut produire des octets differents — re-encodage,
        redimensionnement — tout en gardant la meme lettre a l'ecran. Elle ne
        distingue pas davantage une fiche sans image, dont l'avatar est genere,
        d'une fiche qui en porte une.

        On rend donc les faits, sans interpretation : qui porte une image, de
        quelle taille, et lesquelles sont partagees.
        """
        avec = self.filtered("image_1920")
        sans = self - avec
        partages = self._fma_avatars_partages()
        details = []
        for employe in avec[:12]:
            image = employe.image_1920
            taille = len(image if isinstance(image, bytes) else image.encode())
            details.append("• %s — %s ko" % (employe.name, taille // 1024))
        if len(avec) > 12:
            details.append("• … et %s autres" % (len(avec) - 12))
        message = _(
            "%(avec)s fiche(s) portent une image, %(sans)s n'en portent aucune."
            "\n\nUne fiche SANS image affiche un avatar genere par Odoo. Une "
            "fiche AVEC image affiche cette image, meme si elle ressemble a un "
            "avatar : c'est le cas apres une duplication.\n\n%(details)s"
            "\n\n%(partages)s",
            avec=len(avec), sans=len(sans),
            details="\n".join(details) or "—",
            partages=(
                _("%s groupe(s) d'images strictement identiques.", len(partages))
                if partages else
                _("Aucune image strictement identique entre deux fiches.")
            ),
        )
        return self._fma_notifier(_("État des images"), message)

    def action_fma_vider_photos(self):
        """Vide l'image des fiches selectionnees, sans condition.

        A utiliser quand le diagnostic montre que les fiches portent bien une
        image mais que celle-ci n'est pas une vraie photo. La selection est le
        garde-fou : c'est l'utilisateur qui designe les fiches, pas une
        heuristique.
        """
        avec = self.filtered("image_1920")
        if not avec:
            return self._fma_notifier(
                _("Rien à vider"),
                _("Aucune des %s fiches sélectionnées ne porte d'image.", len(self)),
            )
        avec.write({"image_1920": False})
        _logger.info("FMA : image videe sur %s fiche(s) employe.", len(avec))
        return self._fma_notifier(
            _("Image vidée sur %s fiche(s)", len(avec)),
            _("Chacune retrouve l'avatar généré par Odoo à partir de son nom. "
              "Une vraie photo peut être reposée ensuite."),
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
