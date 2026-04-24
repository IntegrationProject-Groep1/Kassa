"""
Test suite for pos_profiles.py.

Covers:
  - Both profiles created when absent
  - Existing profiles are updated (write), not re-created
  - "Cash (Inschrijving)" is created when absent (create_if_missing)
  - "Cash (Inschrijving)" is looked up (not re-created) when already present
  - Bar Kassa uses "Cash"; Inschrijvingskassa uses "Cash (Inschrijving)"
  - Bar Kassa includes Badge Wallet; Inschrijvingskassa does not
  - Missing method without create_if_missing is skipped with a warning
  - Two-phase execution: ALL pm lookups before ANY pos.config upsert
  - write skips payment_method_ids when current and desired sets are equal
  - write includes payment_method_ids only when the sets differ
  - RuntimeError raised when pm_ids is empty for a profile with required Cash/Card
  - Exceptions propagate out of ensure_pos_profiles (no swallowing)
"""
import pytest
from unittest.mock import MagicMock, patch

import pos_profiles


# ---------------------------------------------------------------------------
# Constants & fixtures
# ---------------------------------------------------------------------------

URL = "http://test:8069"
DB = "test_db"
UID = 1
PASS = "test_pass"

_PM_CASH = [{"id": 10}]
_PM_CARD = [{"id": 20}]
_PM_BADGE = [{"id": 30}]
_PM_CASH_INSCHRIJVING = [{"id": 40}]
_CASH_INSCHRIJVING_NEW_ID = 40


@pytest.fixture
def models():
    return MagicMock()


@pytest.fixture
def patched_proxy(models):
    with patch("pos_profiles.xmlrpc.client.ServerProxy", return_value=models):
        yield models


# ---------------------------------------------------------------------------
# Helpers: standard side_effect lists (two-phase order)
#
# Phase 1 — all pm resolutions (Bar Kassa then Inschrijvingskassa)
# Phase 2 — all pos.config upserts (Bar Kassa then Inschrijvingskassa)
# ---------------------------------------------------------------------------

def _side_effect_both_absent(bar_id=10, inschrijving_id=11):
    """
    Ten calls: both POS configs absent, "Cash (Inschrijving)" needs creation.

    Phase 1 (6 calls):
      Bar Kassa:          Cash, Card, Badge Wallet lookups
      Inschrijvingskassa: Cash (Inschrijving) miss + create, Card lookup
    Phase 2 (4 calls):
      Bar Kassa:          config search → absent, config create
      Inschrijvingskassa: config search → absent, config create
    """
    return [
        # Phase 1 — Bar Kassa pm lookups
        _PM_CASH, _PM_CARD, _PM_BADGE,
        # Phase 1 — Inschrijvingskassa pm lookups
        [], _CASH_INSCHRIJVING_NEW_ID,  # Cash (Inschrijving): miss → create
        _PM_CARD,
        # Phase 2 — Bar Kassa config
        [], bar_id,
        # Phase 2 — Inschrijvingskassa config
        [], inschrijving_id,
    ]


def _side_effect_both_absent_cash_exists(bar_id=10, inschrijving_id=11):
    """
    Nine calls: both configs absent, "Cash (Inschrijving)" already present.

    Phase 1 (5 calls):
      Bar Kassa:          Cash, Card, Badge Wallet lookups
      Inschrijvingskassa: Cash (Inschrijving) found, Card lookup
    Phase 2 (4 calls):
      Both configs: search → absent, create
    """
    return [
        # Phase 1
        _PM_CASH, _PM_CARD, _PM_BADGE,
        _PM_CASH_INSCHRIJVING, _PM_CARD,
        # Phase 2
        [], bar_id,
        [], inschrijving_id,
    ]


# ---------------------------------------------------------------------------
# Creation tests
# ---------------------------------------------------------------------------

def test_creates_bar_kassa_when_absent(patched_proxy):
    patched_proxy.execute_kw.side_effect = _side_effect_both_absent()
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    create_calls = [
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][4] == "create" and c[0][3] == "pos.config"
    ]
    assert "Bar Kassa" in [c[0][5][0]["name"] for c in create_calls]


def test_creates_inschrijvingskassa_when_absent(patched_proxy):
    patched_proxy.execute_kw.side_effect = _side_effect_both_absent()
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    create_calls = [
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][4] == "create" and c[0][3] == "pos.config"
    ]
    assert "Inschrijvingskassa" in [c[0][5][0]["name"] for c in create_calls]


def test_creates_exactly_two_configs_when_both_absent(patched_proxy):
    patched_proxy.execute_kw.side_effect = _side_effect_both_absent()
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    create_calls = [
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][4] == "create" and c[0][3] == "pos.config"
    ]
    assert len(create_calls) == 2


# ---------------------------------------------------------------------------
# Two-phase ordering tests
# ---------------------------------------------------------------------------

def test_all_pm_lookups_before_any_config_upsert(patched_proxy):
    """
    Phase 1 must complete entirely before Phase 2 starts.
    The last pm-related call must precede the first pos.config call.
    """
    patched_proxy.execute_kw.side_effect = _side_effect_both_absent()
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    all_calls = patched_proxy.execute_kw.call_args_list

    # Index of the last call touching pos.payment.method
    last_pm_idx = max(
        i for i, c in enumerate(all_calls)
        if c[0][3] == "pos.payment.method"
    )
    # Index of the first call touching pos.config
    first_config_idx = min(
        i for i, c in enumerate(all_calls)
        if c[0][3] == "pos.config"
    )
    assert last_pm_idx < first_config_idx, (
        f"pm call at index {last_pm_idx} must precede "
        f"first config call at index {first_config_idx}"
    )


def test_cash_inschrijving_created_before_inschrijvingskassa_config(patched_proxy):
    """'Cash (Inschrijving)' create must happen before Inschrijvingskassa pos.config create."""
    patched_proxy.execute_kw.side_effect = _side_effect_both_absent()
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    all_calls = patched_proxy.execute_kw.call_args_list

    cash_create_idx = next(
        i for i, c in enumerate(all_calls)
        if c[0][3] == "pos.payment.method" and c[0][4] == "create"
    )
    inschrijving_config_idx = next(
        i for i, c in enumerate(all_calls)
        if c[0][3] == "pos.config" and c[0][4] in ("create", "write")
        and (
            (c[0][4] == "create" and c[0][5][0].get("name") == "Inschrijvingskassa")
            or (c[0][4] == "write")
        )
    )
    assert cash_create_idx < inschrijving_config_idx


# ---------------------------------------------------------------------------
# Cash (Inschrijving) — dedicated cash method tests
# ---------------------------------------------------------------------------

def test_inschrijvingskassa_creates_cash_inschrijving_when_absent(patched_proxy):
    """When 'Cash (Inschrijving)' is not in Odoo it must be created with is_cash_count=True."""
    patched_proxy.execute_kw.side_effect = _side_effect_both_absent()
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    pm_create_calls = [
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][4] == "create" and c[0][3] == "pos.payment.method"
    ]
    assert len(pm_create_calls) == 1
    vals = pm_create_calls[0][0][5][0]
    assert vals["name"] == "Cash (Inschrijving)"
    assert vals["is_cash_count"] is False


def test_inschrijvingskassa_does_not_recreate_cash_inschrijving_when_present(patched_proxy):
    """When 'Cash (Inschrijving)' already exists no create call is made."""
    patched_proxy.execute_kw.side_effect = _side_effect_both_absent_cash_exists()
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    pm_create_calls = [
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][4] == "create" and c[0][3] == "pos.payment.method"
    ]
    assert len(pm_create_calls) == 0


def test_bar_kassa_uses_cash_not_cash_inschrijving(patched_proxy):
    """Bar Kassa must look up 'Cash'; it never searches for 'Cash (Inschrijving)'."""
    patched_proxy.execute_kw.side_effect = _side_effect_both_absent()
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    patched_proxy.execute_kw.assert_any_call(
        DB, UID, PASS,
        "pos.payment.method", "search_read",
        [[["name", "=", "Cash"]]],
        {"fields": ["id"], "limit": 1},
    )
    # The only pm create is "Cash (Inschrijving)" — proves "Cash" was found, not created
    pm_create_calls = [
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][3] == "pos.payment.method" and c[0][4] == "create"
    ]
    assert len(pm_create_calls) == 1
    assert pm_create_calls[0][0][5][0]["name"] == "Cash (Inschrijving)"


# ---------------------------------------------------------------------------
# Idempotency (update) tests
# ---------------------------------------------------------------------------

def test_updates_existing_bar_kassa(patched_proxy):
    """Existing Bar Kassa with different pm_ids → write is called with the correct config_id."""
    patched_proxy.execute_kw.side_effect = [
        # Phase 1 — Bar Kassa pm lookups
        _PM_CASH, _PM_CARD, _PM_BADGE,
        # Phase 1 — Inschrijvingskassa: Cash (Inschrijving) absent → create
        [], _CASH_INSCHRIJVING_NEW_ID,
        _PM_CARD,
        # Phase 2 — Bar Kassa config exists with DIFFERENT pm_ids → write with pm update
        [{"id": 99, "payment_method_ids": [1, 2]}], True,
        # Phase 2 — Inschrijvingskassa config absent → create
        [], 50,
    ]
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    write_calls = [
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][4] == "write" and c[0][3] == "pos.config"
    ]
    assert len(write_calls) == 1
    assert write_calls[0][0][5][0] == [99]


def test_updates_both_when_both_exist(patched_proxy):
    """Both configs exist with different pm_ids → two write calls."""
    patched_proxy.execute_kw.side_effect = [
        # Phase 1
        _PM_CASH, _PM_CARD, _PM_BADGE,
        _PM_CASH_INSCHRIJVING, _PM_CARD,
        # Phase 2 — both configs exist with DIFFERENT pm_ids → two writes
        [{"id": 1, "payment_method_ids": [1, 2]}], True,
        [{"id": 2, "payment_method_ids": [3, 4]}], True,
    ]
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    create_calls = [
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][4] == "create" and c[0][3] == "pos.config"
    ]
    write_calls = [
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][4] == "write" and c[0][3] == "pos.config"
    ]
    assert len(create_calls) == 0
    assert len(write_calls) == 2


def test_write_skips_payment_methods_when_unchanged(patched_proxy):
    """When existing config already has the correct pm_ids, write must NOT include payment_method_ids."""
    patched_proxy.execute_kw.side_effect = [
        # Phase 1
        _PM_CASH, _PM_CARD, _PM_BADGE,
        _PM_CASH_INSCHRIJVING, _PM_CARD,
        # Phase 2 — both configs exist with MATCHING pm_ids
        [{"id": 1, "payment_method_ids": [10, 20, 30]}], True,
        [{"id": 2, "payment_method_ids": [40, 20]}], True,
    ]
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    write_calls = [
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][4] == "write" and c[0][3] == "pos.config"
    ]
    assert len(write_calls) == 2
    for wc in write_calls:
        write_vals = wc[0][5][1]
        assert "payment_method_ids" not in write_vals


def test_write_includes_payment_methods_when_changed(patched_proxy):
    """When existing config has different pm_ids, write MUST include payment_method_ids."""
    patched_proxy.execute_kw.side_effect = [
        # Phase 1
        _PM_CASH, _PM_CARD, _PM_BADGE,
        _PM_CASH_INSCHRIJVING, _PM_CARD,
        # Phase 2 — Bar Kassa exists with DIFFERENT pm_ids
        [{"id": 1, "payment_method_ids": [99, 100]}], True,
        # Inschrijvingskassa absent
        [], 2,
    ]
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    write_calls = [
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][4] == "write" and c[0][3] == "pos.config"
    ]
    assert len(write_calls) == 1
    write_vals = write_calls[0][0][5][1]
    assert "payment_method_ids" in write_vals
    assert write_vals["payment_method_ids"] == [(6, 0, [10, 20, 30])]


# ---------------------------------------------------------------------------
# Payment method content tests
# ---------------------------------------------------------------------------

def test_bar_kassa_includes_badge_wallet(patched_proxy):
    patched_proxy.execute_kw.side_effect = _side_effect_both_absent()
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    bar_create = next(
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][4] == "create" and c[0][3] == "pos.config"
        and c[0][5][0].get("name") == "Bar Kassa"
    )
    pm_command = bar_create[0][5][0]["payment_method_ids"][0]
    assert pm_command[0] == 6
    assert 30 in pm_command[2]


def test_inschrijvingskassa_excludes_badge_wallet(patched_proxy):
    patched_proxy.execute_kw.side_effect = _side_effect_both_absent()
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    inschrijving_create = next(
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][4] == "create" and c[0][3] == "pos.config"
        and c[0][5][0].get("name") == "Inschrijvingskassa"
    )
    pm_command = inschrijving_create[0][5][0]["payment_method_ids"][0]
    assert 30 not in pm_command[2]


def test_inschrijvingskassa_has_cash_inschrijving_and_bancontact(patched_proxy):
    patched_proxy.execute_kw.side_effect = _side_effect_both_absent()
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    inschrijving_create = next(
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][4] == "create" and c[0][3] == "pos.config"
        and c[0][5][0].get("name") == "Inschrijvingskassa"
    )
    pm_ids = inschrijving_create[0][5][0]["payment_method_ids"][0][2]
    assert _CASH_INSCHRIJVING_NEW_ID in pm_ids   # Cash (Inschrijving)
    assert 20 in pm_ids                           # Card
    assert 10 not in pm_ids                       # shared "Cash" must NOT appear


def test_inschrijvingskassa_does_not_use_shared_cash(patched_proxy):
    patched_proxy.execute_kw.side_effect = _side_effect_both_absent()
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    inschrijving_create = next(
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][4] == "create" and c[0][3] == "pos.config"
        and c[0][5][0].get("name") == "Inschrijvingskassa"
    )
    pm_ids = inschrijving_create[0][5][0]["payment_method_ids"][0][2]
    assert 10 not in pm_ids


# ---------------------------------------------------------------------------
# Missing payment method (no create_if_missing)
# ---------------------------------------------------------------------------

def test_missing_payment_method_still_creates_profile(patched_proxy):
    """Badge Wallet not found (no create_if_missing) → profile still created."""
    patched_proxy.execute_kw.side_effect = [
        # Phase 1 — Bar Kassa: Badge Wallet missing, no create
        _PM_CASH, _PM_CARD, [],
        # Phase 1 — Inschrijvingskassa
        [], _CASH_INSCHRIJVING_NEW_ID, _PM_CARD,
        # Phase 2 — both absent
        [], 10,
        [], 11,
    ]
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    create_calls = [
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][4] == "create" and c[0][3] == "pos.config"
    ]
    assert len(create_calls) == 2


def test_missing_badge_wallet_excluded_from_bar_kassa(patched_proxy):
    """When Badge Wallet is missing it is not included in Bar Kassa's pm list."""
    patched_proxy.execute_kw.side_effect = [
        # Phase 1
        _PM_CASH, _PM_CARD, [],  # Badge Wallet not found
        [], _CASH_INSCHRIJVING_NEW_ID, _PM_CARD,
        # Phase 2
        [], 10,
        [], 11,
    ]
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    bar_create = next(
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][4] == "create" and c[0][3] == "pos.config"
        and c[0][5][0].get("name") == "Bar Kassa"
    )
    pm_ids = bar_create[0][5][0]["payment_method_ids"][0][2]
    assert 30 not in pm_ids
    assert 10 in pm_ids
    assert 20 in pm_ids


# ---------------------------------------------------------------------------
# Exception handling
# ---------------------------------------------------------------------------

def test_raises_when_pm_ids_empty(patched_proxy):
    """RuntimeError raised when pm_ids is empty for a profile with required Cash/Card."""
    patched_proxy.execute_kw.side_effect = [
        # Phase 1 — Bar Kassa: all methods missing (Cash, Card, Badge Wallet all return [])
        [], [], [],
    ]
    with pytest.raises(RuntimeError):
        pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)


def test_exception_propagates(patched_proxy):
    """Exceptions from execute_kw propagate out of ensure_pos_profiles (no swallowing)."""
    patched_proxy.execute_kw.side_effect = Exception("Odoo is down")
    with pytest.raises(Exception, match="Odoo is down"):
        pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)
