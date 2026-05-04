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
  - Unmanaged POS configs are archived before payment method resolution
  - Two-phase execution: ALL pm lookups before ANY pos.config upsert
  - write always includes payment_method_ids to enforce method ordering
  - RuntimeError raised when Cash or Card cannot be resolved for a profile
  - Exceptions propagate out of ensure_pos_profiles (no swallowing)
"""
import xmlrpc.client

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
COMPANY_ID = 1

_USER_INFO = [{"company_id": [COMPANY_ID, "Test Company"]}]

_PM_CASH = [{"id": 10, "is_cash_count": True}]
_PM_CARD = [{"id": 20, "is_cash_count": False}]
_PM_BADGE = [{"id": 30, "is_cash_count": False}]
_PM_CUSTOMER_ACCOUNT = [{"id": 50, "is_cash_count": False}]
_PM_CASH_INSCHRIJVING = [{"id": 40, "is_cash_count": False}]
_PM_CASH_INSCHRIJVING_WRONG = [{"id": 40, "is_cash_count": True}]
_CASH_INSCHRIJVING_NEW_ID = 40
_CUSTOMER_ACCOUNT_NEW_ID = 50


@pytest.fixture
def models():
    return MagicMock()


@pytest.fixture
def patched_proxy(models):
    with patch("pos_profiles.xmlrpc.client.ServerProxy", return_value=models):
        yield models


# ---------------------------------------------------------------------------
# Helpers: standard side_effect lists
#
# Every call sequence starts with three pre-phase calls:
#   1. res.users.read          → company_id
#   2. pos.category.search_read → categ_map
#   3. pos.config.search_read  → archive check ([] = nothing to archive)
#
# Phase 1 — all pm resolutions (Bar Kassa then Inschrijvingskassa)
# Phase 2 — all pos.config upserts (Bar Kassa then Inschrijvingskassa)
# ---------------------------------------------------------------------------

def _pre_phase(archive_results=None):
    """Three mandatory calls before any payment-method or config work."""
    return [_USER_INFO, [], archive_results if archive_results is not None else []]


def _side_effect_both_absent(bar_id=10, inschrijving_id=11):
    """
    Sixteen calls: both POS configs absent, "Cash (Inschrijving)" and "Customer Account" need creation.

    Pre-phase (3):   res.users, pos.category, pos.config archive search
    Phase 1 (9):     Bar Kassa Cash/Card/Badge/CustomerAcc(miss+create) [5]; 
                     Inschrijvingskassa Cash(Inschrijving)(miss+create), Card, CustomerAcc(found) [4]
    Phase 2 (4):     Bar Kassa search→absent+create; Inschrijvingskassa search→absent+create
    """
    return [
        *_pre_phase(),
        # Phase 1 — Bar Kassa pm lookups
        _PM_CASH, _PM_CARD, _PM_BADGE,
        [], _CUSTOMER_ACCOUNT_NEW_ID,  # Customer Account: miss → create
        # Phase 1 — Inschrijvingskassa pm lookups
        [], _CASH_INSCHRIJVING_NEW_ID,  # Cash (Inschrijving): miss → create
        _PM_CARD, _PM_CUSTOMER_ACCOUNT, # Card: found, Customer Account: found
        # Phase 2 — Bar Kassa config
        [], bar_id,
        # Phase 2 — Inschrijvingskassa config
        [], inschrijving_id,
    ]


def _side_effect_both_absent_cash_exists(bar_id=10, inschrijving_id=11):
    """
    Fourteen calls: both configs absent, all payment methods already present.

    Pre-phase (3):  res.users, pos.category, pos.config archive search
    Phase 1 (7):    Bar Kassa Cash/Card/Badge/CustomerAcc; Inschrijvingskassa Cash(Inschrijving), Card, CustomerAcc
    Phase 2 (4):    Both configs search→absent+create
    """
    return [
        *_pre_phase(),
        # Phase 1
        _PM_CASH, _PM_CARD, _PM_BADGE, _PM_CUSTOMER_ACCOUNT,
        _PM_CASH_INSCHRIJVING, _PM_CARD, _PM_CUSTOMER_ACCOUNT,
        # Phase 2
        [], bar_id,
        [], inschrijving_id,
    ]


# ---------------------------------------------------------------------------
# Archive-before-resolution tests
# ---------------------------------------------------------------------------

def test_archive_called_before_payment_method_resolution(patched_proxy):
    """pos.config archive search_read must precede the first pos.payment.method call."""
    patched_proxy.execute_kw.side_effect = _side_effect_both_absent()
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    all_calls = patched_proxy.execute_kw.call_args_list

    archive_idx = next(
        i for i, c in enumerate(all_calls)
        if c[0][3] == "pos.config" and c[0][4] == "search_read"
    )
    first_pm_idx = min(
        i for i, c in enumerate(all_calls)
        if c[0][3] == "pos.payment.method"
    )
    assert archive_idx < first_pm_idx, (
        f"archive search at index {archive_idx} must precede "
        f"first pm call at index {first_pm_idx}"
    )


def test_unmanaged_config_is_archived(patched_proxy):
    """A pos.config whose name is not in _PROFILES is archived (active=False)."""
    shop_id = 99
    patched_proxy.execute_kw.side_effect = [
        *_pre_phase(archive_results=[{"id": shop_id, "name": "Shop"}]),
        True,  # archive write
        # Phase 1
        _PM_CASH, _PM_CARD, _PM_BADGE, _PM_CUSTOMER_ACCOUNT,
        [], _CASH_INSCHRIJVING_NEW_ID, _PM_CARD, _PM_CUSTOMER_ACCOUNT,
        # Phase 2
        [], 10,
        [], 11,
    ]
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    patched_proxy.execute_kw.assert_any_call(
        DB, UID, PASS,
        "pos.config", "write",
        [[shop_id], {"active": False}],
    )


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
    """Phase 1 (all pm work) must complete entirely before Phase 2 (pos.config create/write)."""
    patched_proxy.execute_kw.side_effect = _side_effect_both_absent()
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    all_calls = patched_proxy.execute_kw.call_args_list

    last_pm_idx = max(
        i for i, c in enumerate(all_calls)
        if c[0][3] == "pos.payment.method"
    )
    first_config_upsert_idx = min(
        i for i, c in enumerate(all_calls)
        if c[0][3] == "pos.config" and c[0][4] in ("create", "write")
    )
    assert last_pm_idx < first_config_upsert_idx, (
        f"pm call at index {last_pm_idx} must precede "
        f"first config upsert at index {first_config_upsert_idx}"
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
        if c[0][3] == "pos.config" and c[0][4] == "create"
        and c[0][5][0].get("name") == "Inschrijvingskassa"
    )
    assert cash_create_idx < inschrijving_config_idx


# ---------------------------------------------------------------------------
# Cash (Inschrijving) — dedicated cash method tests
# ---------------------------------------------------------------------------

def test_inschrijvingskassa_creates_cash_inschrijving_when_absent(patched_proxy):
    """When 'Cash (Inschrijving)' is not in Odoo it must be created with is_cash_count=False."""
    patched_proxy.execute_kw.side_effect = _side_effect_both_absent()
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    pm_create_calls = [
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][4] == "create" and c[0][3] == "pos.payment.method"
    ]
    # One for Customer Account (Bar Kassa phase), one for Cash (Inschrijving)
    assert len(pm_create_calls) == 2
    vals = next(c[0][5][0] for c in pm_create_calls if c[0][5][0]["name"] == "Cash (Inschrijving)")
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


def test_inschrijvingskassa_normalizes_existing_cash_inschrijving_flags(patched_proxy):
    """Existing 'Cash (Inschrijving)' is corrected to is_cash_count=False when needed."""
    patched_proxy.execute_kw.side_effect = [
        *_pre_phase(),
        # Phase 1 — Bar Kassa pm lookups
        _PM_CASH, _PM_CARD, _PM_BADGE, _PM_CUSTOMER_ACCOUNT,
        # Phase 1 — Inschrijvingskassa: method exists but is misconfigured
        _PM_CASH_INSCHRIJVING_WRONG,
        True,  # write() that normalizes is_cash_count
        _PM_CARD, _PM_CUSTOMER_ACCOUNT,
        # Phase 2 — both configs absent
        [], 10,
        [], 11,
    ]

    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    patched_proxy.execute_kw.assert_any_call(
        DB, UID, PASS,
        "pos.payment.method", "write",
        [[40], {"is_cash_count": False}],
    )


def test_bar_kassa_uses_cash_not_cash_inschrijving(patched_proxy):
    """Bar Kassa must look up 'Cash' (with company scope); it never creates a dedicated method."""
    patched_proxy.execute_kw.side_effect = _side_effect_both_absent()
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    patched_proxy.execute_kw.assert_any_call(
        DB, UID, PASS,
        "pos.payment.method", "search_read",
        [[["name", "=", "Cash"], ["company_id", "=", COMPANY_ID]]],
        {"fields": ["id", "is_cash_count"], "limit": 1},
    )
    # pm creations: "Customer Account" and "Cash (Inschrijving)"
    pm_create_calls = [
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][3] == "pos.payment.method" and c[0][4] == "create"
    ]
    assert len(pm_create_calls) == 2
    assert any(c[0][5][0]["name"] == "Cash (Inschrijving)" for c in pm_create_calls)


# ---------------------------------------------------------------------------
# Idempotency (update) tests
# ---------------------------------------------------------------------------

def test_updates_existing_bar_kassa(patched_proxy):
    """Existing Bar Kassa → write is called with the correct config_id and payment_method_ids."""
    patched_proxy.execute_kw.side_effect = [
        *_pre_phase(),
        # Phase 1
        _PM_CASH, _PM_CARD, _PM_BADGE, _PM_CUSTOMER_ACCOUNT,
        [], _CASH_INSCHRIJVING_NEW_ID, _PM_CARD, _PM_CUSTOMER_ACCOUNT,
        # Phase 2 — Bar Kassa exists → write
        [{"id": 99}], True,
        # Phase 2 — Inschrijvingskassa absent → create
        [], 50,
    ]
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    write_calls = [
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][4] == "write" and c[0][3] == "pos.config"
    ]
    assert len(write_calls) == 1
    assert write_calls[0][0][5][0] == [99]
    assert "payment_method_ids" in write_calls[0][0][5][1]


def test_updates_both_when_both_exist(patched_proxy):
    """Both configs exist → two write calls."""
    patched_proxy.execute_kw.side_effect = [
        *_pre_phase(),
        # Phase 1
        _PM_CASH, _PM_CARD, _PM_BADGE, _PM_CUSTOMER_ACCOUNT,
        _PM_CASH_INSCHRIJVING, _PM_CARD, _PM_CUSTOMER_ACCOUNT,
        # Phase 2 — both configs exist → two writes
        [{"id": 1}], True,
        [{"id": 2}], True,
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


def test_write_always_includes_payment_method_ids(patched_proxy):
    """payment_method_ids is always written on update — even when ids are unchanged — to enforce order."""
    patched_proxy.execute_kw.side_effect = [
        *_pre_phase(),
        # Phase 1
        _PM_CASH, _PM_CARD, _PM_BADGE, _PM_CUSTOMER_ACCOUNT,
        _PM_CASH_INSCHRIJVING, _PM_CARD, _PM_CUSTOMER_ACCOUNT,
        # Phase 2 — both configs exist (same pm_ids as resolved above)
        [{"id": 1}], True,
        [{"id": 2}], True,
    ]
    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    write_calls = [
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][4] == "write" and c[0][3] == "pos.config"
    ]
    assert len(write_calls) == 2
    for wc in write_calls:
        assert "payment_method_ids" in wc[0][5][1]


def test_write_sets_correct_payment_method_order(patched_proxy):
    """Bar Kassa write must include payment_method_ids in the resolved order (Cash, Card, Badge, Customer Account)."""
    patched_proxy.execute_kw.side_effect = [
        *_pre_phase(),
        # Phase 1
        _PM_CASH, _PM_CARD, _PM_BADGE, _PM_CUSTOMER_ACCOUNT,
        _PM_CASH_INSCHRIJVING, _PM_CARD, _PM_CUSTOMER_ACCOUNT,
        # Phase 2 — Bar Kassa exists → write
        [{"id": 1}], True,
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
    assert write_vals["payment_method_ids"] == [(6, 0, [10, 20, 30, 50])]


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


def test_inschrijvingskassa_has_cash_inschrijving_and_card(patched_proxy):
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
        *_pre_phase(),
        # Phase 1 — Bar Kassa: Badge Wallet missing, no create
        _PM_CASH, _PM_CARD, [], _PM_CUSTOMER_ACCOUNT,
        # Phase 1 — Inschrijvingskassa
        [], _CASH_INSCHRIJVING_NEW_ID, _PM_CARD, _PM_CUSTOMER_ACCOUNT,
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
        *_pre_phase(),
        # Phase 1
        _PM_CASH, _PM_CARD, [], _PM_CUSTOMER_ACCOUNT, # Badge Wallet not found
        [], _CASH_INSCHRIJVING_NEW_ID, _PM_CARD, _PM_CUSTOMER_ACCOUNT,
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
    assert 50 in pm_ids


def test_bar_kassa_recovers_from_cash_method_conflict(patched_proxy):
    """On cash-method exclusivity fault, create a dedicated cash method and retry create."""
    patched_proxy.execute_kw.side_effect = [
        *_pre_phase(),
        # Phase 1 — payment method resolution
        _PM_CASH, _PM_CARD, _PM_BADGE, _PM_CUSTOMER_ACCOUNT,
        [], _CASH_INSCHRIJVING_NEW_ID, _PM_CARD, _PM_CUSTOMER_ACCOUNT,
        # Phase 2 — Bar Kassa config absent, create hits cash conflict
        [],
        xmlrpc.client.Fault(
            2,
            "This cash payment method is already used in another Point of Sale. "
            "A new cash payment method should be created for this Point of Sale.",
        ),
        # Recovery: read current methods, search for dedicated, create dedicated, retry
        [
            {"id": 10, "name": "Cash", "is_cash_count": True},
            {"id": 20, "name": "Card", "is_cash_count": False},
            {"id": 30, "name": "Badge Wallet", "is_cash_count": False},
            {"id": 50, "name": "Customer Account", "is_cash_count": False},
        ],
        [],   # search "Cash (Bar Kassa)" → not found
        110,  # create "Cash (Bar Kassa)"
        10,   # retry pos.config.create → success
        # Phase 2 — Inschrijvingskassa
        [], 11,
    ]

    pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)

    patched_proxy.execute_kw.assert_any_call(
        DB, UID, PASS,
        "pos.payment.method", "create",
        [{"name": "Cash (Bar Kassa)", "is_cash_count": True, "company_id": COMPANY_ID}],
    )

    bar_create_calls = [
        c for c in patched_proxy.execute_kw.call_args_list
        if c[0][3] == "pos.config" and c[0][4] == "create"
        and c[0][5][0].get("name") == "Bar Kassa"
    ]
    assert len(bar_create_calls) == 2
    final_pm_ids = bar_create_calls[-1][0][5][0]["payment_method_ids"][0][2]
    assert 110 in final_pm_ids
    assert 10 not in final_pm_ids


# ---------------------------------------------------------------------------
# Exception handling
# ---------------------------------------------------------------------------

def test_raises_when_pm_ids_empty(patched_proxy):
    """RuntimeError raised when Cash or Card cannot be resolved for a profile."""
    patched_proxy.execute_kw.side_effect = [
        *_pre_phase(),
        # Phase 1 — Bar Kassa: Cash, Card, Badge, Customer all missing
        [], [], [], [], _CUSTOMER_ACCOUNT_NEW_ID,
    ]
    with pytest.raises(RuntimeError):
        pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)


def test_exception_propagates(patched_proxy):
    """Exceptions from execute_kw propagate out of ensure_pos_profiles (no swallowing)."""
    patched_proxy.execute_kw.side_effect = Exception("Odoo is down")
    with pytest.raises(Exception, match="Odoo is down"):
        pos_profiles.ensure_pos_profiles(URL, DB, UID, PASS)
