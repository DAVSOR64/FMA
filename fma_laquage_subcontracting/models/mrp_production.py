# -*- coding: utf-8 -*-
import math
from datetime import datetime, timedelta, time, date as date_type
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)
    laquage_required = fields.Boolean(string='Laquage requis', copy=False, help="Coché automatiquement si l'OF provient d'une commande client taguée F2M.")
    laquage_source_sale_id = fields.Many2one('sale.order', string='Commande source laquage', copy=False, readonly=True)
    laquage_alert_message = fields.Char(string='Alerte laquage', compute='_compute_laquage_alert_message')
    laquage_subcontractor_id = fields.Many2one('res.partner', string='Sous-traitant laquage', copy=False, domain=[('is_laquage_supplier', '=', True)])
    laquage_slot_id = fields.Many2one('fma.laquage.slot', string='Créneau laquage', copy=False)
    laquage_purchase_id = fields.Many2one('purchase.order', string='Achat laquage', copy=False, readonly=True)
    laquage_purchase_line_id = fields.Many2one('purchase.order.line', string='Ligne achat laquage', copy=False, readonly=True)
    laquage_cost = fields.Monetary(string='Coût laquage', currency_field='currency_id', compute='_compute_laquage_cost', store=True)
    laquage_state = fields.Selection([
        ('none', 'Non concerné'),
        ('to_plan', 'À planifier'),
        ('planned', 'Planifié'),
        ('sent', 'Envoyé'),
        ('returned', 'Retourné'),
    ], string='État laquage', default='none', copy=False)

    # -------------------------------------------------------------------------
    # Détection automatique F2M depuis la commande client
    # -------------------------------------------------------------------------
    def _get_laquage_trigger_tag_name(self):
        """Nom du tag SO qui déclenche le laquage.

        Par défaut : F2M.
        Le paramètre système permet de changer le tag sans modifier le code :
        fma_laquage_subcontracting.trigger_sale_tag
        """
        return (self.env['ir.config_parameter'].sudo().get_param(
            'fma_laquage_subcontracting.trigger_sale_tag', 'F2M'
        ) or 'F2M').strip()

    def _get_source_sale_order_for_laquage(self):
        """Retrouve la commande client source de l'OF de manière robuste.

        Selon les flux Odoo/import LOGIKAL, le lien peut venir de sale_id,
        sale_line_id.order_id, procurement_group_id.sale_id ou simplement origin.
        """
        self.ensure_one()
        SaleOrder = self.env['sale.order'].sudo()

        sale = self.env['sale.order']
        if 'sale_id' in self._fields and self.sale_id:
            sale = self.sale_id
        elif 'sale_line_id' in self._fields and self.sale_line_id:
            sale = self.sale_line_id.order_id
        elif self.procurement_group_id:
            if 'sale_id' in self.procurement_group_id._fields and self.procurement_group_id.sale_id:
                sale = self.procurement_group_id.sale_id
            elif self.procurement_group_id.name:
                sale = SaleOrder.search([('name', '=', self.procurement_group_id.name)], limit=1)

        if not sale and self.origin:
            # Origin peut contenir "S00012" ou "S00012, ...".
            origins = [x.strip() for x in self.origin.replace(';', ',').split(',') if x.strip()]
            if origins:
                sale = SaleOrder.search([('name', 'in', origins)], limit=1)
            if not sale:
                sale = SaleOrder.search([('name', '=', self.origin.strip())], limit=1)
        return sale

    def _sale_order_has_laquage_tag(self, sale):
        if not sale or 'tag_ids' not in sale._fields:
            return False
        tag_name = self._get_laquage_trigger_tag_name().lower()
        return tag_name in [name.lower() for name in sale.tag_ids.mapped('name')]

    def _sync_laquage_required_from_sale_tag(self):
        """Coche automatiquement le laquage si le SO source est tagué F2M.

        Important : on ne crée pas le PO ici, car le sous-traitant est choisi
        manuellement par l'opérateur. On crée uniquement l'alerte fonctionnelle.
        """
        for mo in self:
            sale = mo._get_source_sale_order_for_laquage()
            if mo._sale_order_has_laquage_tag(sale):
                vals = {}
                if not mo.laquage_required:
                    vals['laquage_required'] = True
                if mo.laquage_state in (False, 'none'):
                    vals['laquage_state'] = 'to_plan'
                if sale and mo.laquage_source_sale_id != sale:
                    vals['laquage_source_sale_id'] = sale.id
                if vals:
                    mo.with_context(skip_laquage_sync=True).write(vals)
        return True

    @api.depends('laquage_required', 'laquage_state', 'laquage_subcontractor_id')
    def _compute_laquage_alert_message(self):
        for mo in self:
            if mo.laquage_required and mo.laquage_state in ('none', 'to_plan') and not mo.laquage_subcontractor_id:
                mo.laquage_alert_message = _('⚠ Laquage requis pour F2M : choisir le sous-traitant laquage.')
            else:
                mo.laquage_alert_message = False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_laquage_required_from_sale_tag()
        return records

    def write(self, vals):
        res = super().write(vals)
        trigger_fields = {'origin', 'procurement_group_id', 'sale_id', 'sale_line_id'} & set(vals.keys())
        if trigger_fields and not self.env.context.get('skip_laquage_sync'):
            self.with_context(skip_laquage_sync=True)._sync_laquage_required_from_sale_tag()
        return res

    def action_confirm(self):
        res = super().action_confirm()
        self._sync_laquage_required_from_sale_tag()
        return res

    @api.depends('laquage_purchase_line_id.price_subtotal')
    def _compute_laquage_cost(self):
        for mo in self:
            mo.laquage_cost = mo.laquage_purchase_line_id.price_subtotal if mo.laquage_purchase_line_id else 0.0

    def _get_laquage_workorder(self):
        self.ensure_one()
        wo = self.workorder_ids.filtered(lambda w: w.is_external_laquage and w.state not in ('done', 'cancel'))[:1]
        if wo:
            return wo
        candidates = self.workorder_ids.filtered(lambda w: w.state not in ('done', 'cancel') and 'laquage' in ((w.name or '') + ' ' + (w.workcenter_id.name or '')).lower())
        if candidates:
            candidates[0].write({'is_external_laquage': True, 'laquage_state': 'to_plan'})
            return candidates[0]
        return self.env['mrp.workorder']


    def _ensure_laquage_workorder(self, workcenter=False):
        """Retourne l'OT laquage, ou le crée si aucun OT laquage n'existe.

        Utile car LOGIKAL n'envoie pas toujours l'opération de sous-traitance.
        """
        self.ensure_one()
        wo = self._get_laquage_workorder()
        if wo:
            return wo
        if not workcenter:
            workcenter = self.env['mrp.workcenter'].search([('name', '=', 'Laquage F2M')], limit=1)
        if not workcenter:
            raise UserError(_('Aucun poste de travail “Laquage F2M” trouvé. Créez ce poste de travail dans Fabrication > Configuration > Postes de travail.'))
        vals = {
            'name': _('Laquage F2M'),
            'production_id': self.id,
            'workcenter_id': workcenter.id,
            'product_uom_id': self.product_uom_id.id,
            'duration_expected': 0.0,
            'is_external_laquage': True,
            'laquage_state': 'to_plan',
        }
        wo = self.env['mrp.workorder'].create(vals)
        self._resequence_workorders_from_workcenter_code()
        self.message_post(body=_('Opération laquage externe créée automatiquement : %s.') % wo.display_name)
        return wo

    def action_open_laquage_plan_wizard(self):
        self.ensure_one()
        self._sync_laquage_required_from_sale_tag()
        if not self.laquage_required:
            raise UserError(_('Cet OF n’est pas détecté comme F2M : aucune commande source avec le tag laquage n’a été trouvée.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Planifier le laquage'),
            'res_model': 'fma.laquage.plan.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_production_id': self.id},
        }

    def action_laquage_sent(self):
        """Enregistre le départ réel chez le laqueur.

        Après cette action, l'opération est réellement partie : on ne doit plus
        proposer Planifier/Replanifier laquage. Le PO reçoit aussi la date
        réelle pour le suivi fournisseur.
        """
        for mo in self:
            wo = mo._get_laquage_workorder()
            if not wo:
                raise UserError(_('Aucune opération de laquage trouvée.'))
            if mo.laquage_state != 'planned':
                raise UserError(_('Le laquage doit être planifié avant de pouvoir être envoyé.'))
            now = fields.Datetime.now()
            wo_vals = {'laquage_state': 'sent'}
            if 'laquage_departure_real' in wo._fields and not wo.laquage_departure_real:
                wo_vals['laquage_departure_real'] = now
            wo.write(wo_vals)
            mo.write({'laquage_state': 'sent'})

            if mo.laquage_purchase_id:
                po_vals = {}
                if 'laquage_sent_date' in mo.laquage_purchase_id._fields:
                    po_vals['laquage_sent_date'] = now
                if 'laquage_status' in mo.laquage_purchase_id._fields:
                    po_vals['laquage_status'] = 'sent'
                if po_vals:
                    mo.laquage_purchase_id.write(po_vals)
                mo.laquage_purchase_id.message_post(
                    body=_('Départ laquage enregistré depuis l’OF %s le %s.') % (mo.display_name, fields.Datetime.to_string(now))
                )
            mo.message_post(body=_('Laquage envoyé chez le sous-traitant le %s.') % fields.Datetime.to_string(now))
        return True

    def action_laquage_returned(self):
        """Enregistre le retour réel et alerte si le planning doit être revu.

        Le bouton disparaît immédiatement car l'état passe à returned.
        Si la date réelle est différente de la date prévue, on affiche une
        notification pour inviter l'utilisateur à lancer le bouton Replanifier
        standard de l'OF, et non Replanifier laquage.
        """
        notification = False
        for mo in self:
            wo = mo._get_laquage_workorder()
            if not wo:
                raise UserError(_('Aucune opération de laquage trouvée.'))
            if mo.laquage_state != 'sent':
                raise UserError(_('Le laquage doit être envoyé avant de pouvoir enregistrer le retour.'))
            now = fields.Datetime.now()
            wo_vals = {'laquage_state': 'returned'}
            if not wo.laquage_return_real:
                wo_vals['laquage_return_real'] = now
            wo.write(wo_vals)
            mo.write({'laquage_state': 'returned'})

            if mo.laquage_purchase_id:
                po_vals = {}
                if 'laquage_return_date' in mo.laquage_purchase_id._fields:
                    po_vals['laquage_return_date'] = now
                if 'laquage_status' in mo.laquage_purchase_id._fields:
                    po_vals['laquage_status'] = 'returned'
                if po_vals:
                    mo.laquage_purchase_id.write(po_vals)
                mo.laquage_purchase_id.message_post(
                    body=_('Retour laquage enregistré depuis l’OF %s le %s.') % (mo.display_name, fields.Datetime.to_string(now))
                )

            planned = wo.laquage_return_planned
            message = _('Retour laquage enregistré le %s.') % fields.Datetime.to_string(now)
            notif_type = 'success'
            if planned:
                planned_date = fields.Datetime.to_datetime(planned).date()
                real_date = fields.Datetime.to_datetime(now).date()
                delta = (real_date - planned_date).days
                if delta < 0:
                    message = _('Retour laquage enregistré avec %s jour(s) d’avance. Lancez le bouton Replanifier de l’OF si vous voulez avancer les opérations restantes.') % abs(delta)
                    notif_type = 'warning'
                elif delta > 0:
                    message = _('⚠ Retour laquage enregistré avec %s jour(s) de retard. Lancez le bouton Replanifier de l’OF pour recalculer les opérations restantes.') % delta
                    notif_type = 'danger'
            mo.message_post(body=message)
            notification = {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Retour laquage'),
                    'message': message,
                    'type': notif_type,
                    'sticky': True,
                    # Force le rechargement de la fiche OF après fermeture de la notification.
                    # Sans cela, l'état est bien passé à returned côté serveur,
                    # mais le header garde parfois les anciens boutons en cache côté client.
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                }
            }
        return notification or True

    def _compute_laquage_qty(self, subcontractor):
        self.ensure_one()
        field_name = (subcontractor.laquage_qty_field_name or '').strip()
        if field_name and field_name in self._fields:
            qty = getattr(self, field_name, 0.0) or 0.0
            if qty:
                return qty
        return self.product_qty or 1.0


    def _get_laquage_purchase_picking_type(self):
        """Retourne le type de réception achat du même entrepôt que l'OF.

        Sans ça, Odoo prend parfois le type de réception par défaut de la société,
        ce qui crée la réception sur le mauvais warehouse.
        """
        self.ensure_one()
        warehouse = False
        if self.picking_type_id and self.picking_type_id.warehouse_id:
            warehouse = self.picking_type_id.warehouse_id
        if not warehouse and self.location_src_id:
            warehouse = self.env['stock.warehouse'].search([
                ('company_id', '=', self.company_id.id),
                ('view_location_id', 'parent_of', self.location_src_id.id),
            ], limit=1)
        if warehouse and warehouse.in_type_id:
            return warehouse.in_type_id
        return self.env['stock.picking.type'].search([
            ('code', '=', 'incoming'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

    def _get_laquage_purchase_links_vals(self):
        """Champs de liaison OF utilisables selon les modules installés.

        On renseigne notre champ dédié + d'éventuels champs déjà présents dans
        les modules FMA/MTO, sans planter si le champ n'existe pas.
        """
        self.ensure_one()
        po_vals = {}
        pol_vals = {}
        if 'laquage_production_id' in self.env['purchase.order']._fields:
            po_vals['laquage_production_id'] = self.id
        if 'laquage_production_id' in self.env['purchase.order.line']._fields:
            pol_vals['laquage_production_id'] = self.id
        for fname in ('production_id', 'mrp_production_id', 'x_mrp_production_id', 'x_production_id'):
            if fname in self.env['purchase.order.line']._fields:
                pol_vals[fname] = self.id
        return po_vals, pol_vals

    def _ensure_laquage_purchase(self):
        self.ensure_one()
        subcontractor = self.laquage_subcontractor_id
        if not subcontractor:
            raise UserError(_('Aucun sous-traitant laquage sélectionné.'))
        if not subcontractor.laquage_product_id:
            raise UserError(_('Le fournisseur %s n’a pas d’article de service laquage renseigné dans l’onglet Laquage F2M.') % subcontractor.display_name)

        partner = subcontractor
        product = subcontractor.laquage_product_id
        qty = self._compute_laquage_qty(subcontractor)
        wo = self._get_laquage_workorder()
        planned_date = wo.laquage_return_planned or wo.laquage_departure_planned or fields.Datetime.now() if wo else fields.Datetime.now()
        picking_type = self._get_laquage_purchase_picking_type()
        po_link_vals, pol_link_vals = self._get_laquage_purchase_links_vals()

        line_vals = {
            'product_id': product.id,
            'name': '%s - %s' % (product.display_name, self.name),
            'product_qty': qty,
            'product_uom': product.uom_po_id.id or product.uom_id.id,
            'price_unit': subcontractor.laquage_price_unit or product.standard_price or 0.0,
            'date_planned': planned_date,
            **pol_link_vals,
        }

        # Si un achat existe déjà, on le remet à jour au lieu d'en créer un autre.
        if self.laquage_purchase_id and self.laquage_purchase_id.state not in ('cancel',):
            po = self.laquage_purchase_id
            vals_update = {**po_link_vals}
            if picking_type:
                vals_update['picking_type_id'] = picking_type.id
            if 'laquage_status' in po._fields and po.laquage_status not in ('sent', 'returned'):
                vals_update['laquage_status'] = 'to_send'
            if self.procurement_group_id and 'group_id' in po._fields:
                vals_update['group_id'] = self.procurement_group_id.id
            if vals_update:
                po.write(vals_update)
            line = self.laquage_purchase_line_id or po.order_line.filtered(lambda line: line.product_id == product)[:1]
            if line:
                line.write(line_vals)
                self.write({'laquage_purchase_line_id': line.id})
            else:
                line = self.env['purchase.order.line'].create(dict(line_vals, order_id=po.id))
                self.write({'laquage_purchase_line_id': line.id})
            return po

        po_vals = {
            'partner_id': partner.id,
            'company_id': self.company_id.id,
            'origin': self.name,
            'date_order': fields.Datetime.now(),
            'order_line': [(0, 0, line_vals)],
            **po_link_vals,
        }
        if picking_type:
            po_vals['picking_type_id'] = picking_type.id
        if 'laquage_status' in self.env['purchase.order']._fields:
            po_vals['laquage_status'] = 'to_send'
        if self.procurement_group_id and 'group_id' in self.env['purchase.order']._fields:
            # Permet de retrouver le PO depuis l'OF comme les achats MTO du même groupe d'approvisionnement.
            po_vals['group_id'] = self.procurement_group_id.id
        po = self.env['purchase.order'].create(po_vals)
        line = po.order_line[:1]
        self.write({'laquage_purchase_id': po.id, 'laquage_purchase_line_id': line.id})
        self.message_post(body=_('Demande d’achat laquage créée : %s.') % po.display_name)
        return po

    def _previous_weekday_on_or_before(self, day, weekday):
        delta = (day.weekday() - int(weekday)) % 7
        return day - timedelta(days=delta)

    def _compute_slot_departure_from_return(self, return_day, slot):
        dep = int(slot.departure_weekday)
        ret = int(slot.return_weekday)
        delta = (ret - dep) % 7 + (7 * int(slot.return_week_offset or 0))
        return return_day - timedelta(days=delta)

    def _select_laquage_slot_for_deadline(self, subcontractor, latest_return_day):
        """Choisit automatiquement le meilleur créneau du sous-traitant.

        Le wizard ne demande plus le créneau. Le rétroplanning impose le créneau :
        on cherche, parmi les créneaux actifs du fournisseur, celui qui permet un
        retour au plus tard la veille / le jour limite calculé avant le remontage,
        en gardant le retour le plus tard possible pour ne pas avancer inutilement
        les opérations précédentes. À retour identique, on garde le départ le plus
        tardif.
        """
        self.ensure_one()
        slots = subcontractor.laquage_slot_ids.filtered(lambda slot: slot.active)
        if not slots:
            raise UserError(_('Aucun créneau actif n’est configuré sur le fournisseur %s.') % subcontractor.display_name)

        candidates = []
        for slot in slots:
            return_day = self._previous_weekday_on_or_before(latest_return_day, slot.return_weekday)
            departure_day = self._compute_slot_departure_from_return(return_day, slot)
            candidates.append((return_day, departure_day, slot))

        # Dernier retour possible, puis dernier départ possible.
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return candidates[0]

    def action_replanifier_laquage(self):
        """Rétroplanning compatible avec une opération de laquage externe.

        L'opération laquage n'est pas calculée avec une durée atelier, mais avec le créneau
        sous-traitant choisi : départ prévu / retour prévu.
        """
        for mo in self:
            mo._replan_laquage_backward()
        return True


    def _get_laquage_planning_end_date(self):
        """Retourne la vraie date de fin fabrication utilisée par le rétroplanning F2M.

        Priorité au champ Studio affiché sur l'OF : x_studio_date_de_fin.
        Si ce champ est vide mais qu'une date standard existe, on la remonte dans
        le champ Studio pour éviter l'écran "Date de fin" vide côté opérateur.
        """
        self.ensure_one()
        x_end = getattr(self, 'x_studio_date_de_fin', False) or getattr(self, 'x_studio_date_fin', False)
        fallback = False
        for fname in ('date_finished', 'date_deadline', 'date_planned_finished'):
            if fname in self._fields and getattr(self, fname, False):
                fallback = getattr(self, fname)
                break
        if not x_end and fallback:
            x_end = fallback
            if 'x_studio_date_de_fin' in self._fields:
                self.with_context(skip_laquage_sync=True).write({'x_studio_date_de_fin': fields.Date.to_date(fallback)})
        return x_end

    def _replan_laquage_backward(self):
        self.ensure_one()
        if not self.laquage_subcontractor_id:
            raise UserError(_('Sélectionnez d’abord un sous-traitant laquage.'))
        laquage_wo = self._get_laquage_workorder()
        if not laquage_wo:
            raise UserError(_('Aucune opération de laquage externe trouvée sur cet OF.'))

        x_end = self._get_laquage_planning_end_date()
        if not x_end:
            raise UserError(_('Renseignez une date de fin fabrication avant de replanifier.'))
        if not isinstance(x_end, date_type):
            x_end = fields.Date.to_date(x_end)

        workorders = self._get_replannable_workorders_from_date_fin()
        if not workorders:
            raise UserError(_('Aucune opération non commencée à replanifier.'))

        current_end_day = x_end
        payloads = []
        for wo in workorders.sorted(lambda w: (w.op_sequence or 9999, w.id), reverse=True):
            wc = wo.workcenter_id
            if wo.id == laquage_wo.id or wo.is_external_laquage:
                return_day, departure_day, selected_slot = self._select_laquage_slot_for_deadline(
                    self.laquage_subcontractor_id, current_end_day
                )
                if self.laquage_slot_id != selected_slot:
                    self.with_context(skip_laquage_sync=True).write({'laquage_slot_id': selected_slot.id})
                start_dt = self._morning_dt(departure_day, wc) if wc else datetime.combine(departure_day, time(7, 30))
                end_dt = self._morning_dt(return_day, wc) if wc else datetime.combine(return_day, time(7, 30))
                vals = {
                    'is_external_laquage': True,
                    'laquage_state': 'planned',
                    'laquage_departure_planned': start_dt,
                    'laquage_return_planned': end_dt,
                }
                wo.write(vals)
                self._write_wo_schedule_debug(wo, start_dt, start_dt, end_dt, 0)
                current_end_day = self._previous_working_day(departure_day, wc)
            else:
                cal = wc.resource_calendar_id or self.env.company.resource_calendar_id if wc else self.env.company.resource_calendar_id
                hours_per_day = cal.hours_per_day if cal else 7.8
                duration_hours, nb_resources = self._get_effective_duration_hours(wo)
                required_days = max(1, int(math.ceil(duration_hours / (hours_per_day or 7.8))))
                last_day = self._previous_or_same_working_day(current_end_day, wc)
                first_day = last_day
                for day_idx in range(required_days - 1):
                    first_day = self._previous_working_day(first_day, wc)
                start_dt = self._morning_dt(first_day, wc) if wc else datetime.combine(first_day, time(7, 30))
                end_dt = self._evening_dt(last_day, wc) if wc else datetime.combine(last_day, time(17, 0))
                self._write_wo_schedule_debug(wo, start_dt, start_dt, end_dt, nb_resources)
                current_end_day = self._previous_working_day(first_day, wc)
            payloads.append({
                'wo': wo,
                'macro_dt': start_dt,
                'start_dt': start_dt,
                'end_dt': end_dt,
                'nb_resources': 0 if wo.is_external_laquage else getattr(wo, 'x_nb_resources', 1) or 1,
            })

        end_dt = self._evening_dt(x_end, workorders[-1].workcenter_id) if workorders[-1].workcenter_id else datetime.combine(x_end, time(17, 0))
        self._update_mo_dates_from_macro(forced_end_dt=end_dt)
        self._restore_wo_schedule_after_mo_update(payloads)
        self._update_components_picking_dates()
        self.write({'laquage_required': True, 'laquage_state': 'planned'})
        self._ensure_laquage_purchase()
        return True



    def _get_laquage_and_standard_purchase_orders(self):
        """Retourne les achats standard de l'OF + l'achat de laquage.

        Le smart button natif Achats d'un OF Odoo/purchase_mrp ne récupère
        généralement que les PO issus des mouvements composants MTO. Le laquage
        est un service, donc il n'a pas de mouvement stock destinataire. On force
        ici la liste avec notre champ dédié + origin/group_id.
        """
        PurchaseOrder = self.env['purchase.order']
        PurchaseOrderLine = self.env['purchase.order.line']
        orders = PurchaseOrder
        for mo in self:
            if mo.laquage_purchase_id:
                orders |= mo.laquage_purchase_id
            if 'laquage_production_id' in PurchaseOrder._fields:
                orders |= PurchaseOrder.search([('laquage_production_id', '=', mo.id)])
            if 'laquage_production_id' in PurchaseOrderLine._fields:
                orders |= PurchaseOrderLine.search([('laquage_production_id', '=', mo.id)]).mapped('order_id')
            # Achats standard reliés à l'OF par groupe ou mouvements MTO.
            if mo.procurement_group_id:
                if 'group_id' in PurchaseOrder._fields:
                    orders |= PurchaseOrder.search([('group_id', '=', mo.procurement_group_id.id)])
                domains = []
                if 'move_dest_ids' in PurchaseOrderLine._fields:
                    domains.append([('move_dest_ids.group_id', '=', mo.procurement_group_id.id)])
                if 'group_id' in PurchaseOrder._fields:
                    domains.append([('order_id.group_id', '=', mo.procurement_group_id.id)])
                domains.append([('order_id.origin', 'ilike', mo.name)])
                for domain in domains:
                    try:
                        orders |= PurchaseOrderLine.search(domain).mapped('order_id')
                    except Exception:
                        pass
            if mo.name:
                orders |= PurchaseOrder.search([('origin', 'ilike', mo.name), ('company_id', '=', mo.company_id.id)])
        return orders

    def _action_view_purchase_orders_with_laquage(self):
        """Action liste PO compatible avec plusieurs noms de boutons Odoo."""
        self.ensure_one()
        orders = self._get_laquage_and_standard_purchase_orders()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Bon de commande généré de %s') % (self.display_name or self.name),
            'res_model': 'purchase.order',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', orders.ids)],
            'context': dict(self.env.context, create=False),
        }
        if len(orders) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': orders.id,
                'views': [(False, 'form')],
            })
        return action

    # Noms possibles selon version/module Odoo pour le smart button Achats OF.
    def action_view_purchase_orders(self):
        return self._action_view_purchase_orders_with_laquage()

    def action_view_purchase_order(self):
        return self._action_view_purchase_orders_with_laquage()

    def action_view_mrp_production_purchaseorders(self):
        return self._action_view_purchase_orders_with_laquage()

    def action_view_mrp_production_purchase_orders(self):
        return self._action_view_purchase_orders_with_laquage()

    def action_view_purchase(self):
        return self._action_view_purchase_orders_with_laquage()

    def _compute_purchase_order_count(self):
        """Étend le compteur natif si le champ existe dans la base."""
        try:
            super()._compute_purchase_order_count()
        except AttributeError:
            pass
        for mo in self:
            count = len(mo._get_laquage_and_standard_purchase_orders())
            for fname in ('purchase_order_count', 'purchase_count'):
                if fname in mo._fields:
                    try:
                        setattr(mo, fname, count)
                    except Exception:
                        pass

    # -------------------------------------------------------------------------
    # Intégration avec le smart button Achats standard Odoo / purchase_mrp
    # -------------------------------------------------------------------------
    def _get_purchase_orders(self):
        # Méthode utilisée par certains modules : on renvoie la liste complète.
        try:
            purchase_orders = super()._get_purchase_orders()
        except AttributeError:
            purchase_orders = self.env['purchase.order']
        return purchase_orders | self._get_laquage_and_standard_purchase_orders()

    def _build_replan_preview_payload(self):
        """Ajoute les achats de laquage au popup de replanification existant."""
        payload = super()._build_replan_preview_payload()
        existing_names = {po.get('name') for po in payload.get('purchase_orders', [])}
        for po in self._get_purchase_orders().filtered(lambda order: order.partner_id.is_laquage_supplier):
            if po.name in existing_names:
                continue
            planned_dates = po.order_line.filtered(lambda line: line.date_planned).mapped('date_planned')
            planned_date = min(planned_dates) if planned_dates else False
            payload.setdefault('purchase_orders', []).append({
                'name': po.name or '',
                'partner': po.partner_id.display_name or '',
                'date_planned': str(planned_date)[:10] if planned_date else '',
            })
        return payload

    def button_mark_done(self):
        for mo in self:
            if mo.laquage_required and mo.laquage_state not in ('returned', 'none'):
                raise UserError(_('Impossible de clôturer l’OF : le retour laquage n’est pas enregistré.'))
        return super().button_mark_done()
