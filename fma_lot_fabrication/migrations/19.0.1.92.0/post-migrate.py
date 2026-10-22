"""Repose l'atelier, le chantier et l'affaire sur les OF qui les ont perdus.

La scission par numero de serie passe par ``_get_backorder_mo_vals``, qui
construit un dictionnaire et ne copie pas l'ordre : tout champ absent de ce
dictionnaire etait perdu. Une ligne de 5 menuiseries donnait donc 1 ordre
complet et 4 reliquats sans atelier — hors du macro-planning et des
restitutions de capacite, qui raisonnent par atelier. L'OF de debit, lui,
n'est jamais scinde : il gardait le sien, d'ou l'ecart que l'atelier
constatait entre debit et assemblage.

Le correctif ne vaut que pour les ordres a venir. Ceux qui existent sont
repris ici, a la meme regle : l'atelier de l'etiquette de la commande
(FMA -> La Regrippiere, F2M -> La Remaudiere), le chantier et l'affaire du
lot. Rien n'est ecrase : seuls les champs VIDES sont remplis.

Les ordres annules sont laisses de cote — les remettre au planning n'aurait
pas de sens.
"""
import logging

_logger = logging.getLogger(__name__)

CHAMPS_LOT = ("x_studio_projet_de_la_vente", "x_studio_mtn_mrp_sale_order")


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api
    env = api.Environment(cr, SUPERUSER_ID, {})
    Production = env["mrp.production"]
    if "atelier_id" not in Production._fields:
        _logger.info(
            "fma_lot_fabrication : fma_atelier absent, reprise sans objet.")
        return
    lots = env["fma.lot.fabrication"].search([("state", "!=", "cancel")])
    poses, sans_atelier = 0, []
    for lot in lots:
        ordres = lot.production_ids.filtered(lambda p: p.state != "cancel")
        if not ordres:
            continue
        # Les valeurs d'en-tete que la generation pose sur un ordre neuf. On
        # les relit du lot plutot que de les recopier d'un ordre frere : un
        # ordre frere peut lui-meme etre un reliquat ampute.
        atelier = lot._atelier_par_etiquette()
        if not atelier:
            sans_atelier.append(lot.display_name)
        # Encadre : _get_picking_type refuse un lot dont rien ne designe
        # l'atelier, et une reprise ne doit pas s'arreter sur un lot bancal.
        # L'atelier, lui, se pose quand meme s'il a ete trouve.
        try:
            vals_lot = lot._common_production_vals(lot._get_picking_type())
        except Exception as erreur:  # noqa: BLE001 — trace, pas d'arret
            env.invalidate_all()
            _logger.warning(
                "Reprise du lot %s : en-tete illisible (%s), seul l'atelier "
                "est repris.", lot.display_name, erreur)
            vals_lot = {}
        for ordre in ordres:
            vals = {}
            if atelier and not ordre.atelier_id:
                vals["atelier_id"] = atelier.id
            for champ in CHAMPS_LOT:
                if champ in Production._fields and not ordre[champ] \
                        and vals_lot.get(champ):
                    vals[champ] = vals_lot[champ]
            if not vals:
                continue
            try:
                ordre.write(vals)
                poses += 1
            except Exception as erreur:  # noqa: BLE001 — trace, pas d'arret
                env.invalidate_all()
                _logger.warning(
                    "Reprise de %s impossible : %s", ordre.display_name,
                    erreur)
    env.flush_all()
    _logger.info(
        "fma_lot_fabrication : %s ordre(s) repris (atelier / chantier / "
        "affaire) sur %s lot(s)%s",
        poses, len(lots),
        (" ; atelier introuvable pour : " + ", ".join(sans_atelier[:20]))
        if sans_atelier else "")
