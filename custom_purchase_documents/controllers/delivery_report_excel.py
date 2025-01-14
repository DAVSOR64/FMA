from odoo import http
from odoo.http import request
import xlsxwriter
import io

class DeliveryReportExcel(http.Controller):

    @http.route(['/report/delivery/excel/<int:delivery_id>'], type='http', auth="user", csrf=False)
    def generate_excel_report(self, delivery_id, **kwargs):
        # Vérifier que le bon de livraison existe
        picking = request.env['stock.picking'].browse(delivery_id)
        if not picking.exists():
            return request.not_found()

        # Création du fichier Excel en mémoire
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Bon de Livraison')

        # Style pour les cellules en gras
        bold = workbook.add_format({'bold': True})

        # En-têtes de colonnes
        worksheet.write(0, 0, 'Référence du bon de livraison', bold)
        worksheet.write(0, 1, 'Client', bold)
        worksheet.write(0, 2, 'Date prévue de livraison', bold)
        worksheet.write(0, 3, 'Article', bold)
        worksheet.write(0, 4, 'Quantité commandée', bold)
        worksheet.write(0, 5, 'Quantité livrée', bold)

        # Remplir les données du bon de livraison
        row = 1
        for move in picking.move_lines:
            worksheet.write(row, 0, picking.name)
            worksheet.write(row, 1, picking.partner_id.name or '')
            worksheet.write(row, 2, str(picking.scheduled_date) or '')
            worksheet.write(row, 3, move.product_id.name or '')
            worksheet.write(row, 4, move.product_uom_qty or 0)
            worksheet.write(row, 5, move.quantity_done or 0)
            row += 1

        # Fermer le workbook pour finaliser l'écriture
        workbook.close()

        # Réinitialiser le pointeur du buffer pour préparer la lecture
        output.seek(0)

        # Créer la réponse HTTP avec le fichier Excel
        response = request.make_response(
            output.getvalue(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', 'attachment; filename=bon_de_livraison.xlsx;')
            ]
        )

        # Fermer le flux BytesIO
        output.close()

        return response
