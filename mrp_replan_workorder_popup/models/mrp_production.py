def action_open_replan_preview(self):
    self.ensure_one()

    workorders = self.workorder_ids.filtered(
        lambda w: w.state not in ("done", "cancel")
    )

    if not workorders:
        raise UserError(_("Aucune opération à recalculer"))

    def _wo_start(wo):
        return (
            getattr(wo, "macro_planned_start", False)
            or getattr(wo, "date_start", False)
            or False
        )

    def _wo_end(wo):
        return (
            getattr(wo, "macro_planned_end", False)
            or getattr(wo, "date_finished", False)
            or False
        )

    # SNAPSHOT compatible Odoo 17 / custom
    snapshot = {
        "wo": {
            wo.id: {
                "start": _wo_start(wo),
                "end": _wo_end(wo),
            }
            for wo in workorders
        },
        "mo_start": self.date_start,
        "mo_end": (
            getattr(self, "date_planned_finished", False)
            or getattr(self, "date_finished", False)
            or self.date_deadline
            or getattr(self, "macro_forced_end", False)
        ),
    }

    fixed_end = (
        getattr(self, "macro_forced_end", False)
        or self.date_deadline
        or getattr(self, "date_finished", False)
        or getattr(self, "date_planned_finished", False)
    )

    if not fixed_end:
        raise UserError(_("Aucune date de fin n'est définie sur l'OF."))

    # calcul réel en simulation
    self._run_real_replan(fixed_end)

    new_start = self.date_start
    new_end = (
        getattr(self, "date_planned_finished", False)
        or getattr(self, "date_finished", False)
        or fixed_end
    )

    # restore snapshot
    for wo in workorders:
        data = snapshot["wo"][wo.id]

        if hasattr(wo, "macro_planned_start"):
            wo.macro_planned_start = data["start"]
        elif hasattr(wo, "date_start"):
            wo.date_start = data["start"]

        if hasattr(wo, "macro_planned_end"):
            wo.macro_planned_end = data["end"]
        elif hasattr(wo, "date_finished"):
            wo.date_finished = data["end"]

    self.date_start = snapshot["mo_start"]
    if hasattr(self, "date_finished"):
        self.date_finished = snapshot["mo_end"]

    html = f"""
        <p><b>Début :</b> {new_start or '-'}</p>
        <p><b>Fin :</b> {new_end or '-'}</p>
    """

    wiz = self.env["mrp.replan.preview.wizard"].create({
        "production_id": self.id,
        "preview_json": json.dumps({"end": str(fixed_end)}),
        "summary_html": html,
    })

    return {
        "type": "ir.actions.act_window",
        "res_model": "mrp.replan.preview.wizard",
        "res_id": wiz.id,
        "view_mode": "form",
        "target": "new",
    }