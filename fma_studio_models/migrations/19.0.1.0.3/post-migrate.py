# -*- coding: utf-8 -*-
"""Re-run of 19.0.1.0.2's repoint migration.

19.0.1.0.2 was applied to the staging DB without going through a genuine
upgrade transition (ir_module_module already showed 19.0.1.0.2 with the
old studio_customization actions still linked to the Configuration menus:
Gamme mtn/Serie mtn/Reglements kept opening actions 1070/1071/1089).
Bumping the version again forces Odoo to actually run this step.
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

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
    _logger.info(
        "fma_studio_models 19.0.1.0.3: found %d studio_customization window actions",
        len(studio_actions),
    )

    total_repointed = 0
    for res_model, new_xmlid in _NEW_ACTION_XMLID_BY_MODEL.items():
        new_action = env.ref(new_xmlid, raise_if_not_found=False)
        if not new_action:
            _logger.warning(
                "fma_studio_models 19.0.1.0.3: xmlid %s not found, skipping %s",
                new_xmlid, res_model,
            )
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
            _logger.info(
                "fma_studio_models 19.0.1.0.3: repointing %d menu(s) for %s"
                " (old action ids %s) -> action %s (id %d)",
                len(menus), res_model, old_actions.ids, new_xmlid, new_action.id,
            )
            menus.write({"action": "ir.actions.act_window,%d" % new_action.id})
            total_repointed += len(menus)

    _logger.info(
        "fma_studio_models 19.0.1.0.3: repointed %d menu(s) in total",
        total_repointed,
    )
