# -*- coding: utf-8 -*-

from . import models

# Technical names ('x_affaire', 'x_capacite_par_poste', ...) that this module
# defines in code and that pre-exist in the target database as Odoo Studio
# "manual" models (ir_model.state = 'manual', same tables/columns, no data
# migration). Must match the model list in models/__init__.py.
STUDIO_MODEL_NAMES = [
    "x_affaire", "x_affaire_stage", "x_affaire_tag",
    "x_capacite_par_poste", "x_capacite_par_poste_tag",
    "x_delai_entre_operatio", "x_delai_entre_operatio_line_07ffc", "x_delai_entre_operatio_tag",
    "x_gamme_mtn", "x_serie_mtn",
    "x_reglements",
    "x_remise", "x_remises", "x_remise_affaire", "x_remises_affaire",
    "x_remise_chantier", "x_remise_chantier_line_46d7e", "x_remise_chantier_line_da285",
    "x_purchase_order_line_35a7b", "x_account_move_line_803a2",
]


def pre_init_hook(env):
    """Flip the pre-existing Studio "manual" ir.model rows to 'base' before
    this module's own code-defined models are set up.

    Odoo rebuilds a dynamic model class for every ir_model row still marked
    'manual' on every registry setup pass (odoo/orm/model_classes.py,
    _add_manual_models), and that dynamic class unconditionally overwrites
    whatever real Python class this module just registered for the same
    name. As long as these rows say 'manual', the real classes defined in
    models/*.py never "win", so ir.model.access.csv (which references
    e.g. 'model_x_affaire') fails to resolve and the whole install aborts.

    This only touches the ir_model.state column -- it does not touch the
    underlying tables or any business data.
    """
    env.cr.execute(
        "UPDATE ir_model SET state = 'base' WHERE model = ANY(%s) AND state = 'manual'",
        (STUDIO_MODEL_NAMES,),
    )
