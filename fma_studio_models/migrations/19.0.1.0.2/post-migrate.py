# -*- coding: utf-8 -*-
"""Repoint menu items still using the original Odoo Studio actions to the
versioned actions now provided by this module.

Confirmed on staging: the "Gamme mtn" entry under Ventes > Configuration
still opened studio_customization's own window action for x_gamme_mtn
(external id studio_customization.gamme_mtn_46b3e27c-...), whose Studio
form view crashes the Owl renderer on v19 ("this.child.mount is not a
function"). Porting the model/views to this module (see STUDIO_AUDIT.md)
never repointed the pre-existing Studio menu items, so they kept opening
the old, broken action. Same risk flagged for every other x_* model ported
here -- fixed for all of them at once instead of one crash report at a
time.

Only the menu's `action` field is changed; the old studio_customization
action/view records are left untouched (in case something else still
depends on them).
"""
from odoo import api, SUPERUSER_ID

_NEW_ACTION_XMLID_BY_MODEL = {
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


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    IrActWindow = env["ir.actions.act_window"]
    IrModelData = env["ir.model.data"]
    IrUiMenu = env["ir.ui.menu"]

    studio_action_ids = IrModelData.search([
        ("module", "=", "studio_customization"),
        ("model", "=", "ir.actions.act_window"),
    ]).mapped("res_id")
    studio_actions = IrActWindow.browse(studio_action_ids).exists()

    for res_model, new_xmlid in _NEW_ACTION_XMLID_BY_MODEL.items():
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
