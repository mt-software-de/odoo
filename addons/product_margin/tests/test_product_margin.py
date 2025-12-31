# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestProductMargin(AccountTestInvoicingCommon):
    def setUp(self):
        super().setUp()
        self.supplier = self.env['res.partner'].create({'name': 'Supplier'})
        self.customer = self.env['res.partner'].create({'name': 'Customer'})
        self.ipad = self.env['product.product'].create({
            'name': 'Ipad',
            'standard_price': 500.0,
            'list_price': 750.0,
        })

    def test_product_margin(self):
        ''' In order to test the product_margin module '''

        supplier = self.supplier
        customer = self.customer
        ipad = self.ipad
        tax = ipad.taxes_id
        tax.price_include = True

        def _get_net_price(quantity, price_unit):
            return tax.compute_all(price_unit, quantity=quantity, product=ipad)["total_excluded"]

        invoices = self.env['account.move'].create([
            {
                'move_type': 'in_invoice',
                'partner_id': supplier.id,
                'invoice_line_ids': [(0, 0, {'product_id': ipad.id, 'quantity': 10.0, 'price_unit': 300.0, 'tax_ids': [(6, 0, tax.ids)]})],
            },
            {
                'move_type': 'in_invoice',
                'partner_id': supplier.id,
                'invoice_line_ids': [(0, 0, {'product_id': ipad.id, 'quantity': 4.0, 'price_unit': 450.0, 'tax_ids': [(6, 0, tax.ids)]})],
            },
            {
                'move_type': 'out_invoice',
                'partner_id': customer.id,
                'invoice_line_ids': [(0, 0, {'product_id': ipad.id, 'quantity': 20.0, 'price_unit': 750.0, 'tax_ids': [(6, 0, tax.ids)]})],
            },
            {
                'move_type': 'out_invoice',
                'partner_id': customer.id,
                'invoice_line_ids': [(0, 0, {'product_id': ipad.id, 'quantity': 10.0, 'price_unit': 550.0, 'tax_ids': [(6, 0, tax.ids)]})],
            },
        ])
        invoices.invoice_date = invoices[0].date
        invoices.action_post()

        result = ipad._compute_product_margin_fields_values()

        # Sale turnover ( Quantity * Price Subtotal / Quantity)
        sale_turnover = (_get_net_price(20.0, 750.00) + _get_net_price(10.0, 550.00))

        # Sale unit avg
        sale_unit_avg = sale_turnover / 30.0

        # Expected sale (Total quantity * Sale price)
        sale_expected = (750.00 * 30.0)

        # Purchase total cost (Quantity * Unit price)
        purchase_total_cost = (_get_net_price(10.0, 300.00) + _get_net_price(4.0, 450.00))

        # Purchase normal cost ( Total quantity * Cost price)
        purchase_normal_cost = (14.0 * 500.00)

        # Purchase unit avg
        purchase_unit_avg = purchase_total_cost / 14.0

        total_margin = sale_turnover - purchase_total_cost
        expected_margin = sale_expected - purchase_normal_cost

        # Check sale unit avg
        self.assertEqual(result[ipad.id]['sale_avg_price'], round(sale_unit_avg, 3), "Wrong Sale Unit Average Pirce")

        # Check purchase unit avg
        self.assertEqual(result[ipad.id]['purchase_avg_price'], purchase_unit_avg, "Wrong Purchase Unit Average Pirce")

        # Check total margin
        self.assertEqual(result[ipad.id]['total_margin'], total_margin, "Wrong Total Margin.")

        # Check expected margin
        self.assertEqual(result[ipad.id]['expected_margin'], expected_margin, "Wrong Expected Margin.")

        refunds = self.env['account.move'].create([
            {
                'move_type': 'in_refund',
                'partner_id': supplier.id,
                'invoice_line_ids': [(0, 0, {'product_id': ipad.id, 'quantity': 10.0, 'price_unit': 100.0, 'tax_ids': [(6, 0, tax.ids)]})],
            },
            {
                'move_type': 'in_refund',
                'partner_id': supplier.id,
                'invoice_line_ids': [(0, 0, {'product_id': ipad.id, 'quantity': 4.0, 'price_unit': 150.0, 'tax_ids': [(6, 0, tax.ids)]})],
            },

            {
                'move_type': 'out_refund',
                'partner_id': customer.id,
                'invoice_line_ids': [(0, 0, {'product_id': ipad.id, 'quantity': 20.0, 'price_unit': 250.0, 'tax_ids': [(6, 0, tax.ids)]})],
            },
            {
                'move_type': 'out_refund',
                'partner_id': customer.id,
                'invoice_line_ids': [(0, 0, {'product_id': ipad.id, 'quantity': 10.0, 'price_unit': 50.0, 'tax_ids': [(6, 0, tax.ids)]})],
            },
        ])
        refunds.invoice_date = invoices[0].date
        refunds.action_post()

        result = ipad._compute_product_margin_fields_values()

        sale_unit_avg_refund = (_get_net_price(20.0, 250.0) + _get_net_price(10.0 , 50.0)) / 30.0
        sale_unit_avg = sale_unit_avg - sale_unit_avg_refund

        purchase_unit_avg_refund = (_get_net_price(10.0, 100.0) + _get_net_price(4.0, 150.0)) / 14.0
        purchase_unit_avg = purchase_unit_avg - purchase_unit_avg_refund

        # Check sale unit avg
        self.assertEqual(result[ipad.id]['sale_avg_price'], sale_unit_avg, "Wrong Sale Unit Average Pirce")
        self.assertEqual(result[ipad.id]['purchase_avg_price'], purchase_unit_avg, "Wrong Purchase Unit Average Pirce")

    def test_sale_avg_price(self):
        customer = self.customer = self.env['res.partner'].create({'name': 'Customer'})
        ipad = self.ipad = self.env['product.product'].create({
            'name': 'Ipad',
            'standard_price': 500.0,
            'list_price': 750.0,
        })
        tax_exclude = ipad.taxes_id
        tax_include = tax_exclude.copy({'price_include': True, "amount": 10.0})
        invoices = self.env['account.move'].create([
            {
                'move_type': 'out_invoice',
                'partner_id': customer.id,
                'invoice_line_ids': [(0, 0, {'product_id': ipad.id, 'quantity': 20.0, 'price_unit': 750.0, 'tax_ids': [(6, 0, tax_exclude.ids)]})],
            },
            {
                'move_type': 'out_invoice',
                'partner_id': customer.id,
                'invoice_line_ids': [(0, 0, {'product_id': ipad.id, 'quantity': 10.0, 'price_unit': 110.0, 'tax_ids': [(6, 0, tax_include.ids)]})],
            },
        ])
        invoices.invoice_date = invoices[0].date
        invoices.action_post()
        result = ipad._compute_product_margin_fields_values()
        sale_avg_price = ((20.0 * 750.0) + (10.0 * 100)) / 30.0
        self.assertEqual(result[ipad.id]['sale_avg_price'], sale_avg_price)
