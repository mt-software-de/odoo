from odoo.tests.common import SavepointCase


class TestBillCorrectedSvls(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ccy = cls.env.company.currency_id
        cls.env.ccy_eur = ccy
        cls.commonSetUp(cls)

    @staticmethod
    def commonSetUp(cls):
        AccountType = cls.env['account.account.type']
        cls.income_account_type = AccountType.create({
            'name': 'Income',
            'type': 'other',
            'internal_group': 'income',
        })

        cls.expense_account_type = AccountType.create({
            'name': 'Expenses',
            'type': 'other',
            'internal_group': 'expense',
        })

        cls.asset_account_type = AccountType.create({
            'name': 'Assets',
            'type': 'other',
            'internal_group': 'asset',
        })

        cls.payable_account_type = AccountType.create({
            'name': 'Payable',
            'type': 'payable',
            'internal_group': 'liability',
        })

        Account = cls.env['account.account']
        cls.account_income = Account.create({
            'name': 'Income Account',
            'code': '44000',
            'user_type_id': cls.income_account_type.id,
        })

        cls.account_expense = Account.create({
            'name': 'Expense Account',
            'code': '54000',
            'user_type_id': cls.expense_account_type.id,
        })

        cls.account_stock_io = Account.create({
            'name': 'Stock Input/Output Account',
            'code': '58800',
            'user_type_id': cls.expense_account_type.id,
        })

        cls.account_stock_valuation = Account.create({
            'name': 'Stock Valuation Account',
            'code': '11430',
            'user_type_id': cls.asset_account_type.id,
        })

        cls.account_payable = Account.create({
            'name': 'Payables',
            'code': '33000',
            'user_type_id': cls.payable_account_type.id,
            'reconcile': True,
        })

        AccountJournal = cls.env['account.journal']
        cls.journal_stock = AccountJournal.create({
            'name': 'Inventory Valuation',
            'code': 'STJ1',
            'type': 'general',
        })
        cls.journal_purchase = AccountJournal.create({
            'name': 'Purchase',
            'code': 'BILL1',
            'type': 'purchase',
        })

        ProductCategory = cls.env['product.category']
        cls.prod_cat_afco = ProductCategory.create({
            'name': 'ProdCatAfco1',
            'property_cost_method': 'average',
            'property_valuation': 'real_time',
            'property_account_income_categ_id': cls.account_income.id,
            'property_account_expense_categ_id': cls.account_expense.id,
            'property_stock_valuation_account_id': cls.account_stock_valuation.id,
            'property_stock_journal': cls.journal_stock.id,
            'property_stock_account_input_categ_id': cls.account_stock_io.id,
            'property_stock_account_output_categ_id': cls.account_stock_io.id,
        })

        Product = cls.env['product.product']
        cls.product0 = Product.create({
            'name': 'ProdSvl1',
            'type': 'product',
            'categ_id': cls.prod_cat_afco.id,
        })

        supplier = cls.env.user.partner_id
        Purchase = cls.env['purchase.order']
        cls.rfq1 = Purchase.create({
            'name': 'rfq1',
            'currency_id': cls.env.ccy_eur.id,
            'partner_id': supplier.id,
            'order_line': [(0, 0, {
                'name': cls.product0.name,
                'product_id': cls.product0.id,
                'product_qty': 10,
                'price_unit': 50,
            })],
        })
        supplier.property_account_payable_id = cls.account_payable.id

        def action_create_invoice(self, order, bill_unit_price):
            order = order.with_company(order.company_id)
            invoice_vals = order._prepare_invoice()
            line_vals = order.order_line._prepare_account_move_line()
            line_vals.update({'price_unit': bill_unit_price})
            line_vals.update({'sequence': 10})
            invoice_vals['invoice_line_ids'].append((0, 0, line_vals))
            AccountMove = self.env['account.move'].with_context(default_move_type='in_invoice')
            return AccountMove.with_company(invoice_vals['company_id']).create(invoice_vals)

        cls.create_invoice_from_order_with_patched_price = action_create_invoice

    def test_bill_corrected_svl(self):
        order = self.rfq1.with_context(test_queue_job_no_delay=True)
        Svl = self.env['stock.valuation.layer']
        Aml = self.env['account.move.line']
        svl_start = Svl.search([])
        aml_start = Aml.search([])

        self.assertEqual(self.product0.standard_price, 0)

        order.button_confirm()
        picking = order.picking_ids

        picking.move_lines.move_line_ids.write({'qty_done': 4})
        picking._action_done()

        svl = Svl.search([]) - svl_start
        aml = Aml.search([]) - aml_start
        self.assertEqual(self.product0.standard_price, 50)
        self.assertEqual(svl.value, 200.0)
        self.assertEqual(aml.mapped('balance'), [-200.0, 200.0])
        self.assertEqual(aml.account_id, self.account_stock_io + self.account_stock_valuation)

        # We cannot just call order.action_create_invoice, because subsequent
        # price unit change would need to be handled via NewId and onchanges;
        # instead we provide patched invoice line vals, and let move.create
        # auto-create payable peer line
        invoice = self.create_invoice_from_order_with_patched_price(order, 60.0)
        self.assertEqual(self.product0.standard_price, 50)
        aml = Aml.search([("journal_id", "=", self.journal_stock.id)])
        self.assertEqual(len(aml), 2) # i.e. still only one valuation move

        invoice.invoice_date = order.date_order
        invoice.action_post()

        svl = Svl.search([])
        aml = Aml.search([
            ("journal_id", "=", self.journal_stock.id),
            ("balance", "!=", 0)]) - aml
        self.assertEqual(self.product0.standard_price, 60)
        self.assertEqual(svl.mapped('value'), [200.0, 40.0])
        self.assertEqual(aml.mapped('balance'), [-40.0, 40.0])
        self.assertEqual(aml.account_id, self.account_stock_io + self.account_stock_valuation)

    #def test_landing_costs_svl(self):
        # Todo

class TestBillCorrectedSvlsFx(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # to test for absence of balance key error in case of:
        # purchase order line currency being different from company's ccy
        ccy = cls.env.company.currency_id
        fx = ccy.search([]) - ccy
        fx_company = cls.env.companies.create({
            'name': 'FxCompany',
            'currency_id': fx[0].id
        })
        cls.env.company = fx_company
        cls.env.user.company_id = fx_company
        cls.env.ccy_eur = ccy
        TestBillCorrectedSvls.commonSetUp(cls)

    def test_bill_corrected_svl(self):
        TestBillCorrectedSvls.test_bill_corrected_svl(self)
