# test_main.py – Unit tests for main.py (Odoo auto-setup)
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026

from unittest.mock import MagicMock, patch

import requests

import main


@patch("main.time.sleep", return_value=None)  # avoid actual sleeping in tests
class TestMainSetup:

    # ── wait_for_odoo ────────────────────────────────────────────────────────

    @patch("main.requests.get")
    def test_wait_for_odoo_success(self, mock_get, mock_sleep):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        assert main.wait_for_odoo("http://localhost:8069", timeout=10) is True
        mock_get.assert_called_once()

    @patch("main.requests.get")
    def test_wait_for_odoo_timeout(self, mock_get, mock_sleep):
        mock_get.side_effect = requests.exceptions.RequestException("Conn refused")

        # timeout 10 => 10 // 5 = 2 attempts
        assert main.wait_for_odoo("http://localhost:8069", timeout=10) is False
        assert mock_get.call_count == 2
        assert mock_sleep.call_count == 2

    # ── setup_database ───────────────────────────────────────────────────────

    @patch("main.xmlrpc.client.ServerProxy")
    def test_setup_database_already_exists(self, mock_proxy, mock_sleep):
        mock_common = MagicMock()
        mock_common.authenticate.return_value = 1  # auth success => db accessible
        mock_proxy.return_value = mock_common

        assert main.setup_database("url", "db", "u", "p", "mp") is True
        mock_common.authenticate.assert_called_once()

    @patch("main.requests.post")
    @patch("main.xmlrpc.client.ServerProxy")
    def test_setup_database_create_and_wait(self, mock_proxy, mock_post, mock_sleep):
        mock_common = MagicMock()
        mock_proxy.return_value = mock_common
        # First 2 authenticate calls fail (simulating DB not ready), 3rd succeeds
        mock_common.authenticate.side_effect = [Exception("Not ready"), Exception("Not ready"), 1]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        assert main.setup_database("url", "db", "u", "p", "mp") is True

        mock_post.assert_called_once()
        assert mock_post.call_args[1]["data"]["name"] == "db"
        assert mock_common.authenticate.call_count == 3

    # ── ensure_custom_fields ─────────────────────────────────────────────────

    @patch("main.xmlrpc.client.ServerProxy")
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

        # mock_proxy is called twice: once for common, once for object
        mock_proxy.side_effect = [mock_common, mock_models]

        assert main.ensure_custom_fields("url", "db", "u", "p") is True

        # res.partner has 4 fields, pos.order has 2, product.template has 2
        # So create should be called 8 times.
        create_calls = [c for c in mock_models.execute_kw.call_args_list if c[0][4] == "create"]
        assert len(create_calls) == 8

    @patch("main.xmlrpc.client.ServerProxy")
    def test_ensure_custom_fields_all_present(self, mock_proxy, mock_sleep):
        mock_common, mock_models = MagicMock(), MagicMock()
        mock_common.authenticate.return_value = 1
        mock_proxy.side_effect = [mock_common, mock_models]

        def my_execute_kw(db, uid, pwd, obj, method, args, kw=None):
            if obj == "ir.model" and method == "search_read":
                return [{"id": 10}]
            if obj == "ir.model.fields" and method == "search_read":
                # pretend all fields exist
                return [{"name": "x_user_id"}, {"name": "x_badge_id"},
                        {"name": "x_wallet_balance"}, {"name": "x_date_of_birth"},
                        {"name": "x_rabbitmq_sent"}, {"name": "x_is_topup"},
                        {"name": "x_age_restricted"}, {"name": "x_payment_message_id"}]
            return []

        mock_models.execute_kw.side_effect = my_execute_kw

        assert main.ensure_custom_fields("url", "db", "u", "p") is True

        create_calls = [c for c in mock_models.execute_kw.call_args_list if c[0][4] == "create"]
        assert len(create_calls) == 0

    # ── ensure_pos_installed ─────────────────────────────────────────────────

    @patch("main.xmlrpc.client.ServerProxy")
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

        assert main.ensure_pos_installed("url", "db", "u", "p") is True

    @patch("main.xmlrpc.client.ServerProxy")
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
                # 1st read: uninstalled, 2nd: installed
                return [{"state": "installed" if call_count > 1 else "uninstalled"}]
            if method == "button_immediate_install":
                return True
        mock_models.execute_kw.side_effect = execute_kw

        assert main.ensure_pos_installed("url", "db", "u", "p") is True
        # Check that it pressed the button
        ins_c = [c for c in mock_models.execute_kw.call_args_list if c[0][4] == "button_immediate_install"]
        assert len(ins_c) == 1

    # ── ensure_settings_and_base_data (tax, categories, products, pos_config)

    @patch("main.xmlrpc.client.ServerProxy")
    def test_ensure_tax_settings(self, mock_proxy, mock_sleep):
        mock_common, mock_models = MagicMock(), MagicMock()
        mock_common.authenticate.return_value = 1
        mock_proxy.side_effect = [mock_common, mock_models]

        def execute_kw(db, uid, pwd, obj, method, args, kw=None):
            if obj == "account.tax" and method == "search_read":
                return []  # none exist
            if obj == "account.tax" and method == "create":
                return 55  # mock tax_id
            if obj == "res.company" and method == "search":
                return [1]
            if obj == "product.template" and method == "search":
                return []  # no products to fix
            return True

        mock_models.execute_kw.side_effect = execute_kw

        res = main.ensure_tax_settings("url", "db", "u", "p")
        # should have created all 4 valid rates mapped to tax_id=55
        assert set(res.keys()) == {0.0, 6.0, 12.0, 21.0}
        assert all(v == 55 for v in res.values())

        # company target tax write
        wc = [c for c in mock_models.execute_kw.call_args_list if c[0][4] == "write" and c[0][3] == "res.company"]
        assert len(wc) == 1

    @patch("main.xmlrpc.client.ServerProxy")
    def test_ensure_pos_categories(self, mock_proxy, mock_sleep):
        mock_common, mock_models = MagicMock(), MagicMock()
        mock_common.authenticate.return_value = 1
        mock_proxy.side_effect = [mock_common, mock_models]

        mock_models.execute_kw.return_value = []  # no existing categories

        main.ensure_pos_categories("url", "db", "u", "p")
        # Because we mocked execute_kw to return [], create will be called
        # Our dumb mock returns [] for create too, so ids will be []
        create_calls = [c for c in mock_models.execute_kw.call_args_list if c[0][4] == "create"]
        assert len(create_calls) == 2

    @patch("main.xmlrpc.client.ServerProxy")
    def test_ensure_payment_methods(self, mock_proxy, mock_sleep):
        mock_common, mock_models = MagicMock(), MagicMock()
        mock_common.authenticate.return_value = 1
        mock_proxy.side_effect = [mock_common, mock_models]

        # First return true so they appear existing
        mock_models.execute_kw.return_value = [{"id": 42}]

        pm_ids = main.ensure_payment_methods("url", "db", "u", "p")
        assert len(pm_ids) == 3
        assert pm_ids == [42, 42, 42]

    @patch("main.xmlrpc.client.ServerProxy")
    def test_ensure_pos_config_creates(self, mock_proxy, mock_sleep):
        mock_common, mock_models = MagicMock(), MagicMock()
        mock_common.authenticate.return_value = 1
        mock_proxy.side_effect = [mock_common, mock_models]

        def execute_kw(db, uid, pwd, obj, method, args, kw=None):
            if method == "search_read":
                return []  # No config
            if method == "create":
                return 88
        mock_models.execute_kw.side_effect = execute_kw

        main.ensure_pos_config("url", "db", "u", "p", [1, 2, 3])
        creates = [c for c in mock_models.execute_kw.call_args_list if c[0][4] == "create"]
        assert len(creates) == 1
        assert "Bar Kassa" in creates[0][0][5][0]["name"]
