# -*- coding: utf-8 -*-
"""Self-healing repoint of menu items still opening a Studio-native action.

Two earlier attempts to do this in a migrations/*/post-migrate.py script
never actually ran on staging (Configuration > Gamme mtn/Serie mtn/
Reglements kept opening the old studio_customization actions 1070/1071/
1089 even after the module showed the bumped version installed) -- every
deploy on this environment appears to (re)install this module rather than
upgrade an already-installed one, so version-transition migration scripts
never fire.

_register_hook() runs on every registry build (every server start, every
-i/-u), independent of install-vs-upgrade semantics, so it's the one place
guaranteed to actually execute here. The work itself is idempotent (a
no-op once menus are repointed), so running it on every restart is safe.
"""
import logging

from odoo import models

_logger = logging.getLogger(__name__)

# res_model -> xmlid of the versioned action that replaces the one Odoo
# Studio originally generated (module 'studio_customization') for the same
# model. See STUDIO_AUDIT.md at the repo root for the full background: the
# original Studio form views crash the Owl renderer on v19 ("this.child.mount
# is not a function").
STUDIO_ACTION_REPLACEMENTS = {
    "x_affaire": "fma_studio_models.action_x_affaire",
    "x_affaire_stage": "fma_studio_models.action_x_affaire_stage",
    "x_affaire_tag": "fma_studio_models.action_x_affaire_tag",
    "x_capacite_par_poste": "fma_studio_models.action_x_capacite_par_poste",
    "x_capacite_par_poste_tag": "fma_studio_models.action_x_capacite_par_poste_tag",
    "x_delai_entre_operatio": "fma_studio_models.action_x_delai_entre_operatio",
    "x_delai_entre_operatio_tag": "fma_studio_models.action_x_delai_entre_operatio_tag",
    "x_gamme_mtn": "fma_studio_models.action_x_gamme_mtn",
    "x_serie_mtn": "fma_studio_models.action_x_serie_mtn",
    "x_reglements": "fma_studio_models.action_x_reglements",
    "x_remise": "fma_studio_models.action_x_remise",
    "x_remises": "fma_studio_models.action_x_remises",
    "x_remise_affaire": "fma_studio_models.action_x_remise_affaire",
    "x_remises_affaire": "fma_studio_models.action_x_remises_affaire",
    "x_remise_chantier": "fma_studio_models.action_x_remise_chantier",
}


def repoint_studio_action_menus(env):
    IrActWindow = env["ir.actions.act_window"]
    IrModelData = env["ir.model.data"]
    IrUiMenu = env["ir.ui.menu"]

    studio_action_ids = IrModelData.search([
        ("module", "=", "studio_customization"),
        ("model", "=", "ir.actions.act_window"),
    ]).mapped("res_id")
    if not studio_action_ids:
        return
    studio_actions = IrActWindow.browse(studio_action_ids).exists()

    total_repointed = 0
    for res_model, new_xmlid in STUDIO_ACTION_REPLACEMENTS.items():
        new_action = env.ref(new_xmlid, raise_if_not_found=False)
        if not new_action:
            continue

        old_actions = studio_actions.filtered(
            lambda a, m=res_model: a.res_model == m and a.id != new_action.id
        )
        if not old_actions:
            continue

        menus = IrUiMenu.search([
            ("action", "in", [
                "ir.actions.act_window,%d" % a.id for a in old_actions
            ]),
        ])
        if menus:
            menus.write({"action": "ir.actions.act_window,%d" % new_action.id})
            total_repointed += len(menus)

    if total_repointed:
        _logger.info(
            "fma_studio_models: repointed %d menu(s) from studio_customization"
            " actions to their versioned replacements",
            total_repointed,
        )


# Modeles pour lesquels le module fournit desormais toutes les vues. Toute
# vue Studio restante sur ces modeles est desactivee : Studio genere ses
# formulaires avec un fil de discussion, or ces modeles n'heritent pas de
# mail.thread — la consultation d'un enregistrement plante alors sur
# « 'x_...' object has no attribute '_get_thread_with_access' ».
MODELES_VUES_PORTEES = ("x_reglements",)


def desactiver_vues_studio(env):
    """Desactive les vues Studio des modeles dont le module porte les vues.

    On desactive plutot que de supprimer : le geste est reversible, et une
    vue Studio peut contenir une mise en page que quelqu'un voudra relire
    avant de la perdre.
    """
    IrUiView = env["ir.ui.view"]
    IrModelData = env["ir.model.data"]

    nos_vues = IrModelData.search([
        ("module", "=", "fma_studio_models"),
        ("model", "=", "ir.ui.view"),
    ]).mapped("res_id")

    intruses = IrUiView.search([
        ("model", "in", list(MODELES_VUES_PORTEES)),
        ("id", "not in", nos_vues),
        ("active", "=", True),
    ])
    if intruses:
        intruses.write({"active": False})
        _logger.info(
            "fma_studio_models: %d vue(s) desactivee(s) sur %s — le module "
            "fournit desormais ses propres vues",
            len(intruses), ", ".join(MODELES_VUES_PORTEES),
        )


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    def _register_hook(self):
        super()._register_hook()
        repoint_studio_action_menus(self.env)
        desactiver_vues_studio(self.env)
