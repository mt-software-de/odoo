# Copyright 2023 Camptocamp (https://www.camptocamp.com)

from odoo.tests.common import Form, SavepointCase
from odoo.tools import mute_logger


class TestStockBug(SavepointCase):
    """Test to reproduce and fix bsrau-243."""

    @classmethod
    def _update_qty_in_location(cls, location, product, quantity):
        quants = cls.env["stock.quant"]._gather(product, location, strict=True)
        # this method adds the quantity to the current quantity, so get the diff
        quantity -= sum(quants.mapped("quantity"))
        cls.env["stock.quant"]._update_available_quantity(product, location, quantity)

    @classmethod
    def _create_sale_order(cls, partner, products, partner_shipping=None):
        """Create a sale order for the given `partner`.

        - `products` is a list of tuples `[(product, qty), ...]`
        - `partner_shipping` is an optional delivery address
        """
        sale_form = Form(cls.env["sale.order"])
        sale_form.partner_id = partner
        if partner_shipping:
            sale_form.partner_shipping_id = partner_shipping
        with mute_logger("odoo.tests.common.onchange"):
            for product, qty in products:
                with sale_form.order_line.new() as line:
                    line.product_id = product
                    line.product_uom_qty = qty
        return sale_form.save()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.wh = cls.env["stock.warehouse"].create(
            {
                "name": "Test Warehouse",
                "reception_steps": "one_step",
                "delivery_steps": "pick_ship",
                "code": "WHTEST",
            }
        )
        cls.loc_stock = cls.wh.lot_stock_id
        delivery_pick_rule = cls.wh.delivery_route_id.rule_ids.filtered(
            lambda r: r.location_src_id == cls.loc_stock
        )
        delivery_pick_rule.group_propagation_option = "fixed"

        cls.loc_customer = cls.env.ref("stock.stock_location_customers")

        cls.product1 = cls.env["product.product"].create(
            {"name": "Product 1", "type": "product"}
        )
        cls.product = cls.product1
        cls.partner = cls.env.ref("base.res_partner_4")
        cls.loc_bin1 = cls.env["stock.location"].create(
            {"name": "Bin1", "location_id": cls.loc_stock.id}
        )
        cls.loc_bin2 = cls.env["stock.location"].create(
            {"name": "Bin2", "location_id": cls.loc_stock.id}
        )

        cls._update_qty_in_location(cls.loc_bin1, cls.product, 1)
        cls._update_qty_in_location(cls.loc_bin2, cls.product, 50)

    def test_three_sales_with_related_pickings(self):
        """Check completing picking related to many out picking."""
        # Create the first sale order
        sale1 = self._create_sale_order(self.partner, [(self.product, 5)])
        sale1.warehouse_id = self.wh
        sale1.action_confirm()
        self.assertTrue(sale1.state == 'sale')
        pick_out_1 = sale1.picking_ids
        pick_pick_1 = pick_out_1.move_lines.move_orig_ids.picking_id
        pick_pick_1.action_assign()
        self.assertEqual(pick_pick_1.state, 'assigned')
        # And pick 1 out of 5 product
        ml1 = pick_pick_1.move_line_ids.filtered(lambda ml: ml.product_uom_qty == 1)
        ml1.qty_done = 1
        res = pick_pick_1.button_validate()
        # Create a backorder for the rest of the quantity
        backorder_wiz = (
            self.env["stock.backorder.confirmation"]
            .with_context(res["context"])
            .create({})
        )
        backorder_wiz.process()
        self.assertEqual(pick_pick_1.state, "done")

        sale2 = self._create_sale_order(self.partner, [(self.product, 2)])
        sale2.warehouse_id = self.wh
        sale2.action_confirm()
        self.assertTrue(sale2.state == 'sale')
        pick_out_2 = sale2.picking_ids
        pick_2 = pick_out_1.move_lines.move_orig_ids.picking_id.filtered(
            lambda pick: pick.state != "done"
        )
        pick_2.action_assign()
        self.assertEqual(pick_2.state, 'assigned')
        # And pick 1 out of 6 product
        ml2 = pick_2.move_line_ids
        ml2.qty_done = 1
        res = pick_2.button_validate()
        # Create a backorder for the rest of the quantity
        backorder_wiz = (
            self.env["stock.backorder.confirmation"]
            .with_context(res["context"])
            .create({})
        )
        backorder_wiz.process()
        self.assertEqual(pick_2.state, "done")

        sale3 = self._create_sale_order(self.partner, [(self.product, 1)])
        sale3.warehouse_id = self.wh
        sale3.action_confirm()
        self.assertTrue(sale3.state == 'sale')
        pick_out_3 = sale3.picking_ids
        pick_3 = pick_out_3.move_lines.move_orig_ids.picking_id.filtered(
            lambda pick: pick.state != "done"
        )
        pick_3.action_assign()
        ml3 = pick_3.move_line_ids
        ml3.qty_done = 6

        pick_3.button_validate()
        self.assertEqual(pick_3.state, "done")
        self.assertEqual(pick_out_1.state, "assigned")
        # Without the fix the following OUT pick are not assigned
        self.assertEqual(pick_out_2.state, "assigned")
        self.assertEqual(pick_out_3.state, "assigned")
