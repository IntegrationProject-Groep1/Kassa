# test_main.py – Unit tests for odoo_setup.py (Odoo auto-setup functions)
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026

from unittest.mock import MagicMock, patch

import requests

import odoo_setup


@patch("odoo_setup.time.sleep", return_value=None)  # avoid actual sleeping in tests
class TestMainSetup:

    # ── wait_for_odoo ────────────────────────────────────────────────────────

    @patch("odoo_setup.requests.get")
    def test_wait_for_odoo_success(self, mock_get, mock_sleep):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        assert odoo_setup.wait_for_odoo("http://localhost:8069", timeout=10) is True
        mock_get.assert_called_once()

    @patch("odoo_setup.requests.get")
    def test_wait_for_odoo_timeout(self, mock_get, mock_sleep):
        mock_get.side_effect = requests.exceptions.RequestException("Conn refused")

        # timeout 10 => 10 // 5 = 2 attempts
        assert odoo_setup.wait_for_odoo("http://localhost:8069", timeout=10) is False
        assert mock_get.call_count == 2
        assert mock_sleep.call_count == 2

    # ── setup_database ───────────────────────────────────────────────────────

    @patch("odoo_setup.xmlrpc.client.ServerProxy")
    def test_setup_database_already_exists(self, mock_proxy, mock_sleep):
        mock_common = MagicMock()
        mock_common.authenticate.return_value = 1
        mock_proxy.return_value = mock_common

        assert odoo_setup.setup_database("url", "db", "u", "p", "mp") is True
        mock_common.authenticate.assert_called_once()

    @patch("odoo_setup.requests.post")
    @patch("odoo_setup.xmlrpc.client.ServerProxy")
    def test_setup_database_create_and_wait(self, mock_proxy, mock_post, mock_sleep):
        mock_common = MagicMock()
        mock_proxy.return_value = mock_common
        mock_common.authenticate.side_effect = [Exception("Not ready"), Exception("Not ready"), 1]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        assert odoo_setup.setup_database("url", "db", "u", "p", "mp") is True

        mock_post.assert_called_once()
        assert mock_post.call_args[1]["data"]["name"] == "db"
        assert mock_post.call_args[1]["data"]["demo"] == ""  # falsy string disables demo data
        assert mock_common.authenticate.call_count == 3

    @patch("odoo_setup.requests.post")
    @patch("odoo_setup.xmlrpc.client.ServerProxy")
    def test_setup_database_create_with_demo_enabled(self, mock_proxy, mock_post, mock_sleep):
        mock_common = MagicMock()
        mock_proxy.return_value = mock_common
        mock_common.authenticate.side_effect = [Exception("Not ready"), Exception("Not ready"), 1]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        assert odoo_setup.setup_database("url", "db", "u", "p", "mp", odoo_load_demo=True) is True

        assert mock_post.call_args[1]["data"]["demo"] == "1"  # truthy string enables demo data

    # ── ensure_custom_fields ─────────────────────────────────────────────────

    @patch("odoo_setup.xmlrpc.client.ServerProxy")
    def test_ensure_custom_fields_all_missing(self, mock_proxy, mock_sleep):
        mock_common = MagicMock()
        mock_common.authenticate.return_value = 1

        mock_models = MagicMock()

        def my_execute_kw(db, uid, pwd, obj, method, args, kw=None):
            if obj == "ir.model" and method == "search_read":
                return [{"id": 10}]
            if obj == "ir.model.fields" and method == "search_read":
                return []
            if obj == "ir.model.fields" and method == "create":
                return 99
            return []

        mock_models.execute_kw.side_effect = my_execute_kw
        mock_proxy.side_effect = [mock_common, mock_models]

        assert odoo_setup.ensure_custom_fields("url", "db", "u", "p") is True

        # res.partner has 9 fields, pos.order has 3, product.template has 2 → 14 creates
        create_calls = [c for c in mock_models.execute_kw.call_args_list if c[0][4] == "create"]
        assert len(create_calls) == 14

    @patch("odoo_setup.xmlrpc.client.ServerProxy")
    def test_ensure_custom_fields_all_present(self, mock_proxy, mock_sleep):
        mock_common, mock_models = MagicMock(), MagicMock()
        mock_common.authenticate.return_value = 1
        mock_proxy.side_effect = [mock_common, mock_models]

        def my_execute_kw(db, uid, pwd, obj, method, args, kw=None):
            if obj == "ir.model" and method == "search_read":
                return [{"id": 10}]
            if obj == "ir.model.fields" and method == "search_read":
                return [
                    {"name": "x_user_id"},
                    {"name": "x_badge_id"},
                    {"name": "x_wallet_balance"},
                    {"name": "x_date_of_birth"},
                    {"name": "x_rabbitmq_sent"},
                    {"name": "x_wallet_updated"},
                    {"name": "x_is_topup"},
                    {"name": "x_age_restricted"},
                    {"name": "x_payment_message_id"},
                ]
            return []

        mock_models.execute_kw.side_effect = my_execute_kw

        assert odoo_setup.ensure_custom_fields("url", "db", "u", "p") is True

        create_calls = [c for c in mock_models.execute_kw.call_args_list if c[0][4] == "create"]
        assert len(create_calls) == 0

    # ── ensure_pos_installed ─────────────────────────────────────────────────

    @patch("odoo_setup.xmlrpc.client.ServerProxy")
    def test_ensure_pos_installed_already(self, mock_proxy, mock_sleep):
        mock_common, mock_models = MagicMock(), MagicMock()
        mock_common.authenticate.return_value = 1
        mock_proxy.side_effect = [mock_common, mock_models]

        def execute_kw(db, uid, pwd, obj, method, args, kw=None):
            if method == "search":
                return [1]
            if method == "read":
                return [{"state": "installed"}]
        mock_models.execute_kw.side_effect = execute_kw

        assert odoo_setup.ensure_pos_installed("url", "db", "u", "p") is True

    @patch("odoo_setup.xmlrpc.client.ServerProxy")
    def test_ensure_pos_installed_needs_install(self, mock_proxy, mock_sleep):
        mock_common, mock_models = MagicMock(), MagicMock()
        mock_common.authenticate.return_value = 1
        mock_proxy.side_effect = [mock_common, mock_models]

        call_count = 0

        def execute_kw(db, uid, pwd, obj, method, args, kw=None):
            nonlocal call_count
            if method == "search":
                return [1]
            if method == "read":
                call_count += 1
                return [{"state": "installed" if call_count > 1 else "uninstalled"}]
            if method == "button_immediate_install":
                return True
        mock_models.execute_kw.side_effect = execute_kw

        assert odoo_setup.ensure_pos_installed("url", "db", "u", "p") is True
        ins_c = [c for c in mock_models.execute_kw.call_args_list if c[0][4] == "button_immediate_install"]
        assert len(ins_c) == 1

    # ── ensure_tax_settings ──────────────────────────────────────────────────

    @patch("odoo_setup.xmlrpc.client.ServerProxy")
    def test_ensure_tax_settings(self, mock_proxy, mock_sleep):
        mock_common, mock_models = MagicMock(), MagicMock()
        mock_common.authenticate.return_value = 1
        mock_proxy.side_effect = [mock_common, mock_models]

        def execute_kw(db, uid, pwd, obj, method, args, kw=None):
            if obj == "res.users" and method == "read":
                return [{"company_id": [1, "Test Company"]}]
            if obj == "account.tax" and method == "search_read":
                return []  # none exist → will create
            if obj == "account.tax" and method == "create":
                return 55
            if obj == "res.company" and method == "write":
                return True
            if obj == "product.template" and method == "search":
                return []  # no products to fix
            return True

        mock_models.execute_kw.side_effect = execute_kw

        res = odoo_setup.ensure_tax_settings("url", "db", "u", "p")
        assert set(res.keys()) == {0.0, 6.0, 12.0, 21.0}
        assert all(v == 55 for v in res.values())

        write_calls = [
            c for c in mock_models.execute_kw.call_args_list
            if c[0][4] == "write" and c[0][3] == "res.company"
        ]
        assert len(write_calls) == 1

    # ── ensure_pos_categories ────────────────────────────────────────────────

    @patch("odoo_setup.xmlrpc.client.ServerProxy")
    def test_ensure_pos_categories_creates_two(self, mock_proxy, mock_sleep):
        mock_common, mock_models = MagicMock(), MagicMock()
        mock_common.authenticate.return_value = 1
        mock_proxy.side_effect = [mock_common, mock_models]

        create_ids = iter([101, 102])

        def execute_kw(db, uid, pwd, obj, method, args, kw=None):
            if obj == "pos.category" and method == "search_read":
                return []
            if obj == "pos.category" and method == "create":
                return next(create_ids)
            return []

        mock_models.execute_kw.side_effect = execute_kw

        topup_id, drinks_id = odoo_setup.ensure_pos_categories("url", "db", "u", "p")
        assert (topup_id, drinks_id) == (101, 102)

    @patch("odoo_setup.xmlrpc.client.ServerProxy")
    def test_ensure_pos_categories_no_image_in_create(self, mock_proxy, mock_sleep):
        """Categories are created with just the name — no image or color fields."""
        mock_common, mock_models = MagicMock(), MagicMock()
        mock_common.authenticate.return_value = 1
        mock_proxy.side_effect = [mock_common, mock_models]

        create_ids = iter([101, 102])

        def execute_kw(db, uid, pwd, obj, method, args, kw=None):
            if obj == "pos.category" and method == "search_read":
                return []
            if obj == "pos.category" and method == "create":
                vals = args[0]
                assert set(vals.keys()) == {"name"}, f"unexpected fields in create: {set(vals.keys())}"
                return next(create_ids)
            return []

        mock_models.execute_kw.side_effect = execute_kw

        odoo_setup.ensure_pos_categories("url", "db", "u", "p")

    @patch("odoo_setup.xmlrpc.client.ServerProxy")
    def test_ensure_pos_categories_skips_create_when_present(self, mock_proxy, mock_sleep):
        """When both categories already exist no create call is made."""
        mock_common, mock_models = MagicMock(), MagicMock()
        mock_common.authenticate.return_value = 1
        mock_proxy.side_effect = [mock_common, mock_models]

        def execute_kw(db, uid, pwd, obj, method, args, kw=None):
            if obj == "pos.category" and method == "search_read":
                return [{"id": 5}]
            return []

        mock_models.execute_kw.side_effect = execute_kw

        odoo_setup.ensure_pos_categories("url", "db", "u", "p")

        create_calls = [c for c in mock_models.execute_kw.call_args_list if c[0][4] == "create"]
        assert len(create_calls) == 0

    # ── ensure_payment_methods ───────────────────────────────────────────────

    @patch("odoo_setup.xmlrpc.client.ServerProxy")
    def test_ensure_payment_methods_all_present(self, mock_proxy, mock_sleep):
        mock_common, mock_models = MagicMock(), MagicMock()
        mock_common.authenticate.return_value = 1
        mock_proxy.side_effect = [mock_common, mock_models]

        def execute_kw(db, uid, pwd, obj, method, args, kw=None):
            if obj == "res.users" and method == "read":
                return [{"company_id": [1, "Test"]}]
            return [{"id": 42}]

        mock_models.execute_kw.side_effect = execute_kw

        pm_ids = odoo_setup.ensure_payment_methods("url", "db", "u", "p")
        assert pm_ids == [42, 42, 42]

    @patch("odoo_setup.xmlrpc.client.ServerProxy")
    def test_ensure_payment_methods_creates_missing(self, mock_proxy, mock_sleep):
        """Missing payment methods are created with correct name and is_cash_count flag."""
        mock_common, mock_models = MagicMock(), MagicMock()
        mock_common.authenticate.return_value = 1
        mock_proxy.side_effect = [mock_common, mock_models]

        created = []

        def execute_kw(db, uid, pwd, obj, method, args, kw=None):
            if obj == "res.users" and method == "read":
                return [{"company_id": [1, "Test"]}]
            if obj == "pos.payment.method" and method == "search_read":
                return []  # nothing exists
            if obj == "pos.payment.method" and method == "create":
                created.append(args[0])
                return len(created)
            return []

        mock_models.execute_kw.side_effect = execute_kw

        pm_ids = odoo_setup.ensure_payment_methods("url", "db", "u", "p")
        assert len(pm_ids) == 3
        names = [v["name"] for v in created]
        assert "Cash" in names
        assert "Card" in names
        assert "Badge Wallet" in names
        cash_vals = next(v for v in created if v["name"] == "Cash")
        assert cash_vals["is_cash_count"] is True
        card_vals = next(v for v in created if v["name"] == "Card")
        assert card_vals["is_cash_count"] is False
