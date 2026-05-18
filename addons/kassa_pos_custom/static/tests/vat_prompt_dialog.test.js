/** @odoo-module **/
/**
 * Tests for the VAT prompt dialog flow (Story: BTW-nummer vereist bij factuurvraag).
 *
 * Run with Odoo's Hoot test runner:
 *   docker exec -it <odoo_container> python odoo-bin --test-enable --test-tags kassa_pos_custom
 *
 * What is tested:
 *   1. VAT format validation regex (_isValidVat mirror)
 *   2. VatPromptDialog.confirm() — valid / invalid inputs
 *   3. VatPromptDialog.cancel()
 *   4. PaymentScreen.validate() gate logic (mocked store)
 */

import { describe, expect, test, beforeEach } from "@odoo/hoot";
import { click, fill, press } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";
import { Component, useState, xml } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

// ---------------------------------------------------------------------------
// 1. VAT format validation (mirrors VatPromptDialog._isValidVat)
// ---------------------------------------------------------------------------

/** Identical to the regex in pos_custom.js so we can unit-test it here. */
function isValidVat(val) {
    return /^[A-Z]{2}[A-Z0-9]{6,12}$/i.test((val || "").trim());
}

describe("VAT format validation (_isValidVat)", () => {

    describe("valid EU VAT numbers", () => {
        test("Belgian VAT BE0123456789", () => {
            expect(isValidVat("BE0123456789")).toBe(true);
        });

        test("Belgian VAT BE1234567890", () => {
            expect(isValidVat("BE1234567890")).toBe(true);
        });

        test("Dutch VAT NL123456789B01", () => {
            expect(isValidVat("NL123456789B01")).toBe(true);
        });

        test("German VAT DE123456789", () => {
            expect(isValidVat("DE123456789")).toBe(true);
        });

        test("French VAT FR12345678901", () => {
            expect(isValidVat("FR12345678901")).toBe(true);
        });

        test("French VAT with letter prefix FRXX999999999", () => {
            expect(isValidVat("FRXX999999999")).toBe(true);
        });

        test("Luxembourg LU12345678", () => {
            expect(isValidVat("LU12345678")).toBe(true);
        });

        test("Italy IT12345678901", () => {
            expect(isValidVat("IT12345678901")).toBe(true);
        });

        test("lowercase input be0123456789 (case-insensitive)", () => {
            expect(isValidVat("be0123456789")).toBe(true);
        });

        test("mixed case Be0123456789", () => {
            expect(isValidVat("Be0123456789")).toBe(true);
        });

        test("shortest valid: 2-letter prefix + 6 chars = 8 total", () => {
            expect(isValidVat("BE123456")).toBe(true);
        });

        test("longest valid: 2-letter prefix + 12 chars = 14 total", () => {
            expect(isValidVat("BE1234567890AB")).toBe(true);
        });
    });

    describe("invalid VAT numbers", () => {
        test("empty string", () => {
            expect(isValidVat("")).toBe(false);
        });

        test("null value", () => {
            expect(isValidVat(null)).toBe(false);
        });

        test("undefined value", () => {
            expect(isValidVat(undefined)).toBe(false);
        });

        test("whitespace only", () => {
            expect(isValidVat("   ")).toBe(false);
        });

        test("no country prefix — starts with digit", () => {
            expect(isValidVat("0123456789")).toBe(false);
        });

        test("single-letter prefix B0123456789", () => {
            expect(isValidVat("B0123456789")).toBe(false);
        });

        test("too short — only 5 chars after prefix", () => {
            expect(isValidVat("BE12345")).toBe(false);
        });

        test("too long — 13 chars after prefix", () => {
            expect(isValidVat("BE1234567890123")).toBe(false);
        });

        test("space inside VAT number", () => {
            expect(isValidVat("BE 0123456789")).toBe(false);
        });

        test("dash inside VAT number", () => {
            expect(isValidVat("BE-0123456789")).toBe(false);
        });

        test("dot inside VAT number", () => {
            expect(isValidVat("BE.0123456789")).toBe(false);
        });

        test("numbers only — no country code", () => {
            expect(isValidVat("1234567890")).toBe(false);
        });
    });
});

// ---------------------------------------------------------------------------
// 2. VatPromptDialog component behaviour
// ---------------------------------------------------------------------------

/**
 * Minimal standalone replica of VatPromptDialog used for unit testing.
 * Keeps the same logic as the production component without requiring the
 * full POS environment to be mounted.
 */
class TestableVatDialog extends Component {
    static template = xml`
        <div class="vat-dialog-test">
            <input
                type="text"
                class="vat-input"
                t-model="state.vatNumber"
                t-on-keyup.enter="confirm"
            />
            <div class="error-msg" t-if="state.error" t-esc="state.error"/>
            <button class="btn-confirm" t-on-click="confirm">Bevestigen</button>
            <button class="btn-cancel"  t-on-click="cancel">Annuleren</button>
        </div>
    `;

    static props = {
        partnerName: String,
        onConfirm:   Function,
        onCancel:    Function,
        close:       { type: Function, optional: true },
    };

    setup() {
        this.state = useState({ vatNumber: "", error: "" });
    }

    _isValidVat(val) {
        return /^[A-Z]{2}[A-Z0-9]{6,12}$/i.test((val || "").trim());
    }

    confirm() {
        const vat = this.state.vatNumber.trim().toUpperCase();
        if (!this._isValidVat(vat)) {
            this.state.error = "Ongeldig BTW-nummer. Voorbeeld: BE0123456789";
            return;
        }
        this.props.onConfirm(vat);
        this.props.close?.();
    }

    cancel() {
        this.props.onCancel();
        this.props.close?.();
    }
}

describe("VatPromptDialog component", () => {

    describe("confirm with valid VAT", () => {
        test("calls onConfirm with uppercased trimmed VAT", async () => {
            let confirmed = null;
            const close = () => {};
            const comp = await mountWithCleanup(TestableVatDialog, {
                props: {
                    partnerName: "Jan Peeters",
                    onConfirm: (vat) => { confirmed = vat; },
                    onCancel: () => {},
                    close,
                },
            });

            await fill(".vat-input", "be0123456789");
            await click(".btn-confirm");
            await animationFrame();

            expect(confirmed).toBe("BE0123456789");
        });

        test("no error message shown when VAT is valid", async () => {
            const comp = await mountWithCleanup(TestableVatDialog, {
                props: {
                    partnerName: "Jan Peeters",
                    onConfirm: () => {},
                    onCancel: () => {},
                    close: () => {},
                },
            });

            await fill(".vat-input", "BE0123456789");
            await click(".btn-confirm");
            await animationFrame();

            expect(document.querySelector(".error-msg")).toBe(null);
        });

        test("calls close() after successful confirm", async () => {
            let closeCalled = false;
            const comp = await mountWithCleanup(TestableVatDialog, {
                props: {
                    partnerName: "Jan Peeters",
                    onConfirm: () => {},
                    onCancel: () => {},
                    close: () => { closeCalled = true; },
                },
            });

            await fill(".vat-input", "BE0123456789");
            await click(".btn-confirm");
            await animationFrame();

            expect(closeCalled).toBe(true);
        });

        test("Enter key triggers confirm", async () => {
            let confirmed = null;
            const comp = await mountWithCleanup(TestableVatDialog, {
                props: {
                    partnerName: "Jan Peeters",
                    onConfirm: (vat) => { confirmed = vat; },
                    onCancel: () => {},
                    close: () => {},
                },
            });

            await fill(".vat-input", "BE0123456789");
            await press("Enter");
            await animationFrame();

            expect(confirmed).toBe("BE0123456789");
        });
    });

    describe("confirm with invalid VAT", () => {
        test("shows error message for empty input", async () => {
            const comp = await mountWithCleanup(TestableVatDialog, {
                props: {
                    partnerName: "Jan Peeters",
                    onConfirm: () => {},
                    onCancel: () => {},
                    close: () => {},
                },
            });

            // Leave input empty
            await click(".btn-confirm");
            await animationFrame();

            const errEl = document.querySelector(".error-msg");
            expect(errEl).not.toBe(null);
            expect(errEl.textContent).toContain("Ongeldig BTW-nummer");
        });

        test("shows error for too-short VAT", async () => {
            let confirmed = null;
            const comp = await mountWithCleanup(TestableVatDialog, {
                props: {
                    partnerName: "Jan Peeters",
                    onConfirm: (v) => { confirmed = v; },
                    onCancel: () => {},
                    close: () => {},
                },
            });

            await fill(".vat-input", "BE123");
            await click(".btn-confirm");
            await animationFrame();

            expect(confirmed).toBe(null);
            expect(document.querySelector(".error-msg")).not.toBe(null);
        });

        test("does NOT call onConfirm when VAT is invalid", async () => {
            let confirmed = false;
            const comp = await mountWithCleanup(TestableVatDialog, {
                props: {
                    partnerName: "Jan Peeters",
                    onConfirm: () => { confirmed = true; },
                    onCancel: () => {},
                    close: () => {},
                },
            });

            await fill(".vat-input", "INVALID");
            await click(".btn-confirm");
            await animationFrame();

            expect(confirmed).toBe(false);
        });

        test("does NOT call close() when VAT is invalid", async () => {
            let closeCalled = false;
            const comp = await mountWithCleanup(TestableVatDialog, {
                props: {
                    partnerName: "Jan Peeters",
                    onConfirm: () => {},
                    onCancel: () => {},
                    close: () => { closeCalled = true; },
                },
            });

            await fill(".vat-input", "notvalid");
            await click(".btn-confirm");
            await animationFrame();

            expect(closeCalled).toBe(false);
        });

        test("error cleared and confirm succeeds after correcting invalid input", async () => {
            let confirmed = null;
            const comp = await mountWithCleanup(TestableVatDialog, {
                props: {
                    partnerName: "Jan Peeters",
                    onConfirm: (v) => { confirmed = v; },
                    onCancel: () => {},
                    close: () => {},
                },
            });

            // First attempt — invalid
            await fill(".vat-input", "BAD");
            await click(".btn-confirm");
            await animationFrame();
            expect(confirmed).toBe(null);

            // Second attempt — valid
            await fill(".vat-input", "BE0123456789");
            await click(".btn-confirm");
            await animationFrame();
            expect(confirmed).toBe("BE0123456789");
        });
    });

    describe("cancel", () => {
        test("calls onCancel when cancel button clicked", async () => {
            let cancelled = false;
            const comp = await mountWithCleanup(TestableVatDialog, {
                props: {
                    partnerName: "Jan Peeters",
                    onConfirm: () => {},
                    onCancel: () => { cancelled = true; },
                    close: () => {},
                },
            });

            await click(".btn-cancel");
            await animationFrame();

            expect(cancelled).toBe(true);
        });

        test("calls close() after cancel", async () => {
            let closeCalled = false;
            const comp = await mountWithCleanup(TestableVatDialog, {
                props: {
                    partnerName: "Jan Peeters",
                    onConfirm: () => {},
                    onCancel: () => {},
                    close: () => { closeCalled = true; },
                },
            });

            await click(".btn-cancel");
            await animationFrame();

            expect(closeCalled).toBe(true);
        });

        test("does NOT call onConfirm when cancelled", async () => {
            let confirmed = false;
            const comp = await mountWithCleanup(TestableVatDialog, {
                props: {
                    partnerName: "Jan Peeters",
                    onConfirm: () => { confirmed = true; },
                    onCancel: () => {},
                    close: () => {},
                },
            });

            await click(".btn-cancel");
            await animationFrame();

            expect(confirmed).toBe(false);
        });
    });
});

// ---------------------------------------------------------------------------
// 3. validate() gate logic — unit tests using plain JS (no OWL mount needed)
// ---------------------------------------------------------------------------

/**
 * Extracts the gate condition from PaymentScreen.validate() as a pure function
 * so it can be unit-tested without mounting the full POS.
 *
 * Condition: show the VAT dialog when ALL of:
 *   - order.is_to_invoice() === true
 *   - partner is set (not null)
 *   - partner.is_company === false
 *   - partner.parent_id is falsy (not a company contact)
 *   - partner.vat is empty / null / undefined
 */
function shouldPromptForVat(order, partner) {
    return (
        order.is_to_invoice() &&
        partner != null &&
        !partner.is_company &&
        !partner.parent_id &&
        !(partner.vat || "").trim()
    );
}

function makeOrder({ to_invoice = false } = {}) {
    return { is_to_invoice: () => to_invoice };
}

function makePartner(overrides = {}) {
    return {
        id:         1,
        name:       "Jan Peeters",
        is_company: false,
        parent_id:  null,
        vat:        null,
        ...overrides,
    };
}

describe("validate() gate: shouldPromptForVat", () => {

    describe("cases where dialog SHOULD appear", () => {
        test("private customer, to_invoice=true, no vat", () => {
            expect(shouldPromptForVat(makeOrder({ to_invoice: true }), makePartner())).toBe(true);
        });

        test("private customer, to_invoice=true, vat is empty string", () => {
            expect(shouldPromptForVat(
                makeOrder({ to_invoice: true }),
                makePartner({ vat: "" })
            )).toBe(true);
        });

        test("private customer, to_invoice=true, vat is whitespace", () => {
            expect(shouldPromptForVat(
                makeOrder({ to_invoice: true }),
                makePartner({ vat: "   " })
            )).toBe(true);
        });
    });

    describe("cases where dialog must NOT appear", () => {
        test("to_invoice is false — cashier already cancelled", () => {
            expect(shouldPromptForVat(
                makeOrder({ to_invoice: false }),
                makePartner()
            )).toBe(false);
        });

        test("no partner selected (anonymous order)", () => {
            expect(shouldPromptForVat(makeOrder({ to_invoice: true }), null)).toBe(false);
        });

        test("company customer (is_company=true)", () => {
            expect(shouldPromptForVat(
                makeOrder({ to_invoice: true }),
                makePartner({ is_company: true, vat: null })
            )).toBe(false);
        });

        test("company contact (parent_id set)", () => {
            expect(shouldPromptForVat(
                makeOrder({ to_invoice: true }),
                makePartner({ is_company: false, parent_id: 5, vat: null })
            )).toBe(false);
        });

        test("private customer with existing VAT — no dialog needed", () => {
            expect(shouldPromptForVat(
                makeOrder({ to_invoice: true }),
                makePartner({ vat: "BE0123456789" })
            )).toBe(false);
        });

        test("private customer with existing VAT (lowercase) — no dialog", () => {
            expect(shouldPromptForVat(
                makeOrder({ to_invoice: true }),
                makePartner({ vat: "be0123456789" })
            )).toBe(false);
        });
    });
});

// ---------------------------------------------------------------------------
// 4. VAT normalisation (trimming + uppercasing performed by dialog before save)
// ---------------------------------------------------------------------------

describe("VAT normalisation before ORM write", () => {
    /**
     * The dialog calls: const vat = this.state.vatNumber.trim().toUpperCase();
     * before passing to onConfirm.  These tests verify the transformation.
     */

    function normalise(raw) {
        return (raw || "").trim().toUpperCase();
    }

    test("lowercase is uppercased", () => {
        expect(normalise("be0123456789")).toBe("BE0123456789");
    });

    test("leading spaces are trimmed", () => {
        expect(normalise("  BE0123456789")).toBe("BE0123456789");
    });

    test("trailing spaces are trimmed", () => {
        expect(normalise("BE0123456789  ")).toBe("BE0123456789");
    });

    test("mixed case + spaces", () => {
        expect(normalise("  be0123456789  ")).toBe("BE0123456789");
    });

    test("null input produces empty string", () => {
        expect(normalise(null)).toBe("");
    });

    test("undefined input produces empty string", () => {
        expect(normalise(undefined)).toBe("");
    });
});
