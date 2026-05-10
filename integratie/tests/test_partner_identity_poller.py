import unittest
from unittest.mock import MagicMock, patch
import os

# Set dummy env vars for testing before importing the poller
os.environ["ODOO_URL"] = "http://test-odoo:8069"
os.environ["ODOO_DB"] = "test-db"
os.environ["ODOO_USER"] = "test-user"
os.environ["ODOO_PASS"] = "test-pass"

from partner_identity_poller import PartnerIdentityPoller  # noqa: E402
import identity_client  # noqa: E402


class TestPartnerIdentityPoller(unittest.TestCase):
    def setUp(self):
        self.poller = PartnerIdentityPoller()
        self.poller.uid = 1
        self.poller.models = MagicMock()

    @patch("identity_client.create_user")
    @patch("partner_identity_poller.datetime")
    def test_process_partner_success_create(self, mock_datetime, mock_create_user):
        mock_datetime.utcnow.return_value.strftime.return_value = "2026-05-09 12:00:00"
        mock_create_user.return_value = "new-uuid-123"

        # Mock no existing link in Odoo
        self.poller.models.execute_kw.side_effect = [
            [],  # _find_existing_link_in_odoo search result
            True,  # write result
        ]

        partner = {"id": 101, "name": "Test User", "email": "test@example.com"}
        self.poller.process_partner(partner)

        # Verify Identity call
        mock_create_user.assert_called_once_with("test@example.com", source_system="kassa")

        # Verify Odoo write
        self.poller.models.execute_kw.assert_any_call(
            "test-db",
            1,
            "test-pass",
            "res.partner",
            "write",
            [[101], {
                "x_user_id": "new-uuid-123",
                "x_identity_status": "linked",
                "x_identity_last_sync": "2026-05-09 12:00:00",
            }]
        )

    @patch("identity_client.create_user")
    @patch("identity_client.lookup_by_email")
    def test_process_partner_already_exists_identity(self, mock_lookup, mock_create):
        mock_create.side_effect = identity_client.IdentityEmailAlreadyExists("exists", "test@example.com")
        mock_lookup.return_value = {"master_uuid": "existing-uuid-456"}

        # Mock no existing link in Odoo
        self.poller.models.execute_kw.side_effect = [
            [],  # _find_existing_link_in_odoo
            True,  # write
        ]

        partner = {"id": 102, "name": "Test User 2", "email": "test@example.com"}
        self.poller.process_partner(partner)

        mock_create.assert_called_once()
        mock_lookup.assert_called_once_with("test@example.com")

        # Verify Odoo write with the looked-up UUID
        args, kwargs = self.poller.models.execute_kw.call_args_list[-1]
        self.assertEqual(args[4], "write")
        self.assertEqual(args[5][1]["x_user_id"], "existing-uuid-456")
        self.assertEqual(args[5][1]["x_identity_status"], "linked")

    def test_process_partner_reuse_odoo_link(self):
        # Mock an existing link found in Odoo
        self.poller.models.execute_kw.side_effect = [
            [{"x_user_id": "reused-uuid-789"}],  # _find_existing_link_in_odoo
            True,  # write
        ]

        partner = {"id": 103, "name": "Duplicate User", "email": "dup@example.com"}

        with patch("identity_client.create_user") as mock_create:
            self.poller.process_partner(partner)
            mock_create.assert_not_called()

        # Verify Odoo write with the reused UUID
        args, kwargs = self.poller.models.execute_kw.call_args_list[-1]
        self.assertEqual(args[5][1]["x_user_id"], "reused-uuid-789")
        self.assertEqual(args[5][1]["x_identity_status"], "linked")

    @patch("identity_client.create_user")
    def test_process_partner_identity_unavailable(self, mock_create):
        mock_create.side_effect = identity_client.IdentityUnavailableError("unavailable")

        # Mock no existing link in Odoo
        self.poller.models.execute_kw.side_effect = [
            [],  # _find_existing_link_in_odoo
            True,  # write
        ]

        partner = {"id": 104, "name": "Offline User", "email": "offline@example.com"}
        self.poller.process_partner(partner)

        # Verify Odoo write with 'pending' status
        args, kwargs = self.poller.models.execute_kw.call_args_list[-1]
        self.assertEqual(args[5][1]["x_identity_status"], "pending")
        self.assertNotIn("x_user_id", args[5][1])

    @patch("identity_client.create_user")
    @patch("partner_identity_poller.datetime")
    def test_process_partner_invalid_email(self, mock_datetime, mock_create):
        mock_datetime.utcnow.return_value.strftime.return_value = "2026-05-09 12:00:00"
        # Provide a writable return for the partner update
        self.poller.models.execute_kw.return_value = True

        for bad_email in ["not-an-email", "", "missing@", "@nodomain", None]:
            self.poller.models.execute_kw.reset_mock()
            partner = {"id": 200, "name": "Bad Email User", "email": bad_email}
            self.poller.process_partner(partner)

            # Identity must never be called for an invalid email
            mock_create.assert_not_called()

            # Partner must be written with 'error' status
            write_calls = [
                call for call in self.poller.models.execute_kw.call_args_list
                if call[0][4] == "write"
            ]
            self.assertEqual(len(write_calls), 1)
            self.assertEqual(write_calls[0][0][5][1]["x_identity_status"], "error")


if __name__ == "__main__":
    unittest.main()
