/** @odoo-module **/

/**
 * Kassa POS Custom — Story 9 & 21
 *
 * 1. Patches PosStore to subscribe to "kassa_partner_update" bus events.
 *    On event: fetches only that one partner via RPC and upserts it into the
 *    local partners list — no full reload, no transaction interruption.
 *
 * 2. Registers a reactive OWL effect that fires whenever the current order's
 *    partner changes.  If x_outstanding_amount > 0 and x_session_title is set,
 *    the session-specific product is automatically added to the order at the
 *    outstanding price.  Without a session title no product is auto-added
 *    (cashier handles manually; outstanding-amount badge is still visible).
 *
 * 3. Patches PartnerLine to expose getters used by the XML template to render
 *    the outstanding-amount badge and the session title.
 */

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { PartnerLine } from "@point_of_sale/app/screens/partner_list/partner_line/partner_line";
import { PartnerListScreen } from "@point_of_sale/app/screens/partner_list/partner_list";
import { Component, useState, effect } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { sprintf } from "@web/core/utils/strings";

/** Bus channel published by pos.order.send_partner_bus_event. */
const KASSA_BUS_CHANNEL = "kassa_partner_update";

/** Bus channel published by pos.session.kassa_notify_product_update. */
const KASSA_PRODUCT_CHANNEL = "kassa_product_update";

/**
 * Parse x_session_title into a list of session title strings.
 * Handles three formats: JSON array, plain string (legacy), and empty.
 */
function _parseSessionTitles(raw) {
    if (!raw) return [];
    try {
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) return [String(parsed)].filter(Boolean);
        return parsed
            .map((entry) => (typeof entry === "object" && entry !== null ? entry.title : String(entry)))
            .filter(Boolean);
    } catch {
        return [raw];
    }
}

/** Fields fetched for a single partner on a granular bus-event update. */
const KASSA_PARTNER_FIELDS = [
    "id", "name", "street", "city", "state_id", "country_id",
    "email", "phone", "mobile", "barcode", "vat",
    "is_company", "parent_id", "customer_rank", "active_lang_count",
    "x_wallet_balance", "x_user_id", "x_badge_id",
    "x_outstanding_amount", "x_payment_status", "x_session_title",
    "x_lease_active", "x_lease_id",
];

// ── PosStore patch ────────────────────────────────────────────────────────────

patch(PosStore.prototype, {
    /**
     * Entry point for all Kassa POS customizations.
     * Called once when the POS session is opened.
     */
    async setup() {
        await super.setup(...arguments);
        this._kassaScannedPartnerIds = new Set();
        this._subscribeKassaBusEvents();
        this._watchKassaPartnerSelection();
    },

    /**
     * Register a partner ID as "recently scanned via QR or bus update".
     * PartnerList uses this set to sort these partners to the top of the list.
     */
    kassaRegisterScannedPartner(id) {
        if (id) this._kassaScannedPartnerIds.add(id);
    },

    /**
     * Subscribe to the "kassa_partner_update" Odoo long-polling bus channel.
     *
     * In Odoo 17, two calls are required:
     *   addChannel  — tells the underlying WebSocket to join the channel so
     *                 the server routes bus.bus messages to this session.
     *   subscribe   — registers the JavaScript callback for that notification type.
     *   start()     — activates the connection if not already running.
     */
    _subscribeKassaBusEvents() {
        try {
            this.env.services.bus_service.addChannel(KASSA_BUS_CHANNEL);
            this.env.services.bus_service.subscribe(
                KASSA_BUS_CHANNEL,
                (payload) => {
                    this._onKassaPartnerUpdate(payload).catch((err) =>
                        console.error("[Kassa] Bus handler error:", err)
                    );
                }
            );
            this.env.services.bus_service.addChannel(KASSA_PRODUCT_CHANNEL);
            this.env.services.bus_service.subscribe(
                KASSA_PRODUCT_CHANNEL,
                (payload) => {
                    this._onKassaProductUpdate(payload).catch((err) =>
                        console.error("[Kassa] Product bus handler error:", err)
                    );
                }
            );
            this.env.services.bus_service.start();
        } catch (err) {
            console.warn("[Kassa] Could not subscribe to bus_service:", err);
        }
    },

    /**
     * Register a reactive OWL effect that runs whenever the current order's
     * partner changes.  Accessing selectedOrder and its partner_id inside the
     * effect function makes OWL track those reactive properties automatically,
     * so the effect re-executes on every partner-selection change.
     */
    _watchKassaPartnerSelection() {
        if (this.config?.name !== "Inschrijvingskassa") return;
        try {
            effect(() => {
                const order = this.selectedOrder;
                if (!order) return;

                // partner_id on the OWL-reactive Order object is the partner record.
                // Fallback to get_partner() for legacy Order models.
                const partner =
                    order.partner_id ||
                    (order.get_partner ? order.get_partner() : null);

                // Read x_session_title explicitly so OWL re-fires this effect
                // when session titles arrive asynchronously via the bus event
                // (user_sessions_response is resolved after the QR scan returns).
                void partner?.x_session_title;

                if (partner && (partner.x_outstanding_amount || 0) > 0) {
                    this._kassaAddSessionProducts(order, partner).catch(
                        (err) => console.error("[Kassa] Session product auto-add error:", err)
                    );
                }
            });
        } catch (err) {
            console.warn("[Kassa] Could not register partner-watch effect:", err);
        }
    },

    /**
     * Orchestrator: adds one order line per registered session.
     * The total outstanding amount is split equally across all sessions.
     * Idempotent — already-present lines are skipped on re-runs.
     */
    async _kassaAddSessionProducts(order, partner) {
        const titles = _parseSessionTitles(partner.x_session_title);
        if (!titles.length) {
            console.warn(
                "[Kassa] Geen sessietitels op partner %s — geen product auto-toegevoegd.",
                partner.id
            );
            return;
        }
        const totalOutstanding = partner.x_outstanding_amount || 0;
        // Cent-based distribution: floor each line, give remainder to the last
        // so the sum always equals the exact outstanding amount (no rounding drift).
        const basePerSession = Math.floor((totalOutstanding * 100) / titles.length);
        let remainingCents = Math.round(totalOutstanding * 100);
        for (let i = 0; i < titles.length; i++) {
            const isLast = i === titles.length - 1;
            const priceCents = isLast ? remainingCents : basePerSession;
            await this._kassaAddSessionProduct(order, titles[i], priceCents / 100);
            remainingCents -= priceCents;
        }
    },

    /**
     * Adds a single session product to the order at the given unit price.
     *
     * If the product is not in the POS in-memory catalog (e.g. created by
     * receiver.py after the POS session was already opened), it is fetched
     * from Odoo via a targeted RPC and inserted into the local cache so
     * subsequent scans of the same session don't need another round-trip.
     *
     * Guards:
     *   - Product not found locally nor in Odoo → warn and skip.
     *   - Line already present → skip (idempotent; safe for effect re-runs).
     */
    async _kassaAddSessionProduct(order, sessionTitle, price) {
        // 1. Search the POS in-memory product catalog first (fast path).
        const allProducts =
            this.models?.["product.product"]?.getAll?.() ||
            this.products ||
            [];

        let product = allProducts.find(
            (p) => p.name === sessionTitle || p.display_name === sessionTitle
        );

        // 2. Fallback: product was created while this POS session was already open.
        if (!product) {
            try {
                const results = await this.env.services.orm.searchRead(
                    "product.product",
                    [
                        ["name", "=", sessionTitle],
                        ["available_in_pos", "=", true],
                        ["active", "=", true],
                    ],
                    [
                        "id", "name", "display_name", "list_price", "standard_price",
                        "type", "taxes_id", "barcode", "default_code",
                        "pos_categ_ids", "categ_id", "available_in_pos", "description_sale",
                    ],
                    { limit: 1 }
                );
                if (results && results.length > 0) {
                    const data = results[0];
                    if (this.models?.["product.product"]?.insert) {
                        product = this.models["product.product"].insert(data);
                    } else {
                        product = data;
                        if (this.products) this.products.push(product);
                    }
                    console.log("[Kassa] Sessieproduct '%s' live geladen vanuit Odoo.", sessionTitle);
                }
            } catch (err) {
                console.warn("[Kassa] RPC-fallback voor sessieproduct mislukt:", err);
            }
        }

        if (!product) {
            console.warn(
                "[Kassa] Sessieproduct '%s' niet gevonden — kassier handelt manueel af.",
                sessionTitle
            );
            return;
        }

        // 3. Skip if already in the order.
        const lines =
            order.get_orderlines ? order.get_orderlines() : order.orderlines || [];
        const alreadyPresent = lines.some((l) => {
            const p = l.get_product ? l.get_product() : l.product;
            return p && p.id === product.id;
        });
        if (alreadyPresent) return;

        order.add_product(product, { price });
        console.log("[Kassa] Auto-added '%s' line: €%s", sessionTitle, price.toFixed(2));
    },

    /**
     * Triggered by a "kassa_partner_update" bus event from the integration
     * service.  Fetches only the affected partner via a targeted RPC call and
     * upserts it into the local in-memory partners list.
     *
     * Non-blocking: uses async/await so ongoing POS transactions are never
     * interrupted.
     */
    async _onKassaPartnerUpdate(payload) {
        const partnerId = payload && payload.partner_id;
        if (!partnerId) return;

        try {
            const partners = await this.env.services.orm.read(
                "res.partner",
                [partnerId],
                KASSA_PARTNER_FIELDS
            );
            if (!partners || !partners.length) return;

            const updated = partners[0];
            if (this.models?.["res.partner"]?.insert) {
                this.models["res.partner"].insert(updated);
            } else {
                const idx = this.partners.findIndex((p) => p.id === partnerId);
                if (idx !== -1) {
                    Object.assign(this.partners[idx], updated);
                } else {
                    this.partners.push(updated);
                }
            }
            this.kassaRegisterScannedPartner(partnerId);
            console.log("[Kassa] Partner updated from bus event:", partnerId);
        } catch (err) {
            console.error("[Kassa] Error fetching partner", partnerId, err);
        }
    },

    /**
     * Triggered by a "kassa_product_update" bus event published by
     * pos.session.kassa_notify_product_update after new session products are
     * created or updated.  Fetches the affected products via RPC and upserts
     * them into the reactive model so the product grid re-renders without a
     * manual session reload.
     */
    async _onKassaProductUpdate(payload) {
        const productIds = payload && payload.product_ids;
        if (!productIds || !productIds.length) return;

        try {
            const products = await this.env.services.orm.read(
                "product.product",
                productIds,
                [
                    "id", "name", "display_name", "list_price", "standard_price",
                    "type", "taxes_id", "barcode", "default_code",
                    "pos_categ_ids", "categ_id", "available_in_pos",
                    "description_sale", "x_session_id",
                ]
            );
            for (const product of products || []) {
                if (this.models?.["product.product"]?.insert) {
                    this.models["product.product"].insert(product);
                } else if (this.products) {
                    const idx = this.products.findIndex((p) => p.id === product.id);
                    if (idx !== -1) Object.assign(this.products[idx], product);
                    else this.products.push(product);
                }
            }
            console.log("[Kassa] Synced %d product(s) from kassa_product_update bus event", (products || []).length);
        } catch (err) {
            console.error("[Kassa] Error syncing products from bus event:", err);
        }
    },
});

// ── VatPromptDialog ───────────────────────────────────────────────────────────

/**
 * Modal dialog shown when a private customer requests an invoice but has no
 * VAT number stored in their Odoo partner record.
 *
 * The cashier either enters a valid EU-format VAT number (saved to the partner
 * via ORM before the order is finalised) or clicks "Factuur annuleren" to
 * clear the invoice flag and proceed without one.
 */
class VatPromptDialog extends Component {
    static template = "kassa_pos_custom.VatPromptDialog";
    static components = { Dialog };
    static props = {
        partnerName: String,
        onConfirm: Function,
        onCancel: Function,
        close: Function,
    };

    /**
     * OWL setup hook — initialises reactive dialog state.
     * vatNumber: bound to the <input> field via t-model.
     * error: validation message shown below the input when the format is wrong.
     */
    setup() {
        this.state = useState({ vatNumber: "", error: "" });
    }

    /**
     * Validate a VAT number against the EU format.
     * Expected format: two-letter ISO country code followed by 6–12 alphanumeric
     * characters — e.g. BE0123456789, NL123456789B01, DE123456789.
     *
     * @param {string} val — raw input from the cashier
     * @returns {boolean}
     */
    _isValidVat(val) {
        // Two-letter country code + 6–12 alphanumeric chars — covers all EU formats.
        return /^[A-Z]{2}[A-Z0-9]{6,12}$/i.test(val.trim());
    }

    /**
     * Validate the entered VAT number, invoke onConfirm (which saves it to Odoo),
     * then close the dialog.  If validation fails, show an inline error message
     * and keep the dialog open so the cashier can correct the input.
     */
    async confirm() {
        const vat = this.state.vatNumber.trim().toUpperCase();
        if (!this._isValidVat(vat)) {
            this.state.error = _t("Ongeldig BTW-nummer. Voorbeeld: BE0123456789");
            return;
        }
        await this.props.onConfirm(vat);
        this.props.close();
    }

    /**
     * Dismiss the dialog without saving a VAT number.
     * Calls onCancel so the PaymentScreen can clear the invoice flag.
     */
    cancel() {
        this.props.onCancel();
        this.props.close();
    }
}

// ── PaymentScreen patch ───────────────────────────────────────────────────────

/**
 * - Company customer selected → auto-enable Invoice + add Customer Account.
 * - Selecting "Customer Account" manually → auto-enables Invoice.
 * - Story 19: Badge Wallet hidden via template t-if; safety net in addNewPaymentLine.
 */
patch(PaymentScreen.prototype, {
    /**
     * Look up a payment method by exact name from the POS payment methods list.
     * Supports both the Odoo 17 reactive model API (pos.models["pos.payment.method"])
     * and the legacy flat array (pos.payment_methods) for backwards compatibility.
     *
     * @param {string} name — e.g. "Customer Account", "Badge Wallet"
     * @returns {Object|undefined}
     */
    _kassaFindPm(name) {
        return (
            this.pos.models?.["pos.payment.method"]?.getAll?.() ||
            this.pos.payment_methods || []
        ).find((m) => m.name === name);
    },

    /**
     * Auto-configure the payment screen for a company or linked-contact customer.
     *
     * Fires when the PaymentScreen opens or after the cashier changes the partner.
     * Two actions:
     *   1. Enables "To Invoice" on the order (required for B2B transactions).
     *   2. Adds the "Customer Account" payment method if no payment lines exist yet.
     *
     * Guard: skips entirely if the partner is a private individual without a
     * parent company (is_company=false and parent_id=false).
     * Guard: skips the payment line addition if lines are already present to avoid
     * overriding manual payment choices.
     */
    _kassaActivateCompanyFlow() {
        const order = this.currentOrder;
        const partner = order.get_partner();
        if (!partner || !(partner.is_company || partner.parent_id)) return;
        if (!order.is_to_invoice()) order.set_to_invoice(true);
        const lines = order.get_paymentlines?.() || order.payment_ids || [];
        if (lines.length > 0) return;
        const pm = this._kassaFindPm("Customer Account");
        if (pm) this.addNewPaymentLine(pm);
    },

    /**
     * PaymentScreen OWL setup hook.
     * Calls the parent setup first, then immediately attempts the company flow so
     * company orders that already have a partner set are configured on screen entry.
     */
    setup() {
        super.setup(...arguments);
        try {
            this._kassaActivateCompanyFlow();
        } catch (err) {
            console.warn("[Kassa] Could not auto-activate company flow on entry:", err);
        }
    },

    /**
     * Override of the partner-select button handler.
     * Delegates to the parent implementation (which opens the partner picker),
     * then re-runs the company flow so orders that get a company partner assigned
     * mid-session are configured correctly without a screen reload.
     */
    async selectPartner() {
        await super.selectPartner(...arguments);
        try {
            this._kassaActivateCompanyFlow();
        } catch (err) {
            console.warn("[Kassa] Could not auto-activate company flow after partner select:", err);
        }
    },

    /**
     * Override of addNewPaymentLine with two Kassa-specific guards:
     *
     * Badge Wallet guard (runs before super()):
     *   - Blocks if no partner is selected.
     *   - Blocks if the wallet lease is not yet active (x_lease_active=false) or the
     *     lease ID has not arrived from CRM yet (x_lease_id empty — grant still in flight).
     *   - Blocks if the wallet balance is insufficient for the current order total.
     *     Comparison is done in integer cents to avoid floating-point rounding errors.
     *
     * Customer Account auto-invoice (runs after super()):
     *   - Automatically enables "To Invoice" when a Customer Account line is added,
     *     because Customer Account payments always require a B2B invoice.
     */
    addNewPaymentLine(paymentMethod) {
        if (paymentMethod?.name === "Badge Wallet") {
            const partner = this.currentOrder.get_partner();
            if (!partner) {
                this.env.services.notification.add(
                    _t("Selecteer eerst een klant."),
                    { type: "warning", sticky: false }
                );
                return;
            }
            if (!partner.x_lease_active || !partner.x_lease_id) {
                this.env.services.notification.add(
                    _t("Wallet is nog niet actief. Even geduld en probeer opnieuw."),
                    { type: "warning", sticky: false }
                );
                return;
            }
            const balanceCents = Math.round((partner.x_wallet_balance ?? 0) * 100);
            const dueCents = Math.round(this.currentOrder.get_due() * 100);
            if (balanceCents < dueCents) {
                this.env.services.notification.add(
                    sprintf(_t("Onvoldoende saldo op de wallet (€%s)."), (partner.x_wallet_balance ?? 0).toFixed(2)),
                    { type: "danger", sticky: false }
                );
                return;
            }
        }

        const result = super.addNewPaymentLine(...arguments);
        try {
            if (paymentMethod?.name === "Customer Account" && !this.currentOrder.is_to_invoice()) {
                this.currentOrder.set_to_invoice(true);
            }
        } catch (err) {
            console.warn("[Kassa] Could not auto-enable invoice:", err);
        }
        return result;
    },

    /**
     * Show a dialog asking the cashier to enter a VAT number for a private
     * customer who has none on file.  Resolves with the entered (and saved)
     * VAT string, or null if the cashier cancelled.
     */
    async _kassaPromptVatNumber(partner) {
        return new Promise((resolve) => {
            this.env.services.dialog.add(VatPromptDialog, {
                partnerName: partner.name,
                onConfirm: async (vatNumber) => {
                    try {
                        await this.env.services.orm.write(
                            "res.partner", [partner.id], { vat: vatNumber }
                        );
                        partner.vat = vatNumber;
                        resolve(vatNumber);
                    } catch (err) {
                        console.error("[Kassa] Failed to save VAT to partner:", err);
                        this.env.services.notification.add(
                            _t("Fout bij het opslaan van het BTW-nummer. Factuur geannuleerd."),
                            { type: "danger", sticky: false }
                        );
                        resolve(null);
                    }
                },
                onCancel: () => resolve(null),
            });
        });
    },

    /**
     * Suppress automatic invoice PDF download after order validation.
     * _finalizeValidation gates the download on this method; returning false
     * skips the this.report.doAction("account.account_invoices") call entirely.
     * The invoice is still created server-side.
     */
    shouldDownloadInvoice() {
        return false;
    },

    /**
     * Suppress the automatic invoice PDF download after order validation.
     *
     * The invoice is still created server-side; we just skip the browser download
     * to avoid the cashier screen being interrupted by a PDF prompt.
     * A brief info notification is shown instead so the cashier knows the invoice
     * was generated.
     *
     * @param {number[]} orderIds — Odoo pos.order IDs (not used; PDF suppressed)
     */
    async downloadInvoice(orderIds) {
        this.env.services.notification.add(
            _t("Factuurverzoek ingediend."),
            { type: "info", sticky: false }
        );
    },

    /**
     * Override validate to:
     * 1. Prompt for a VAT number when a private customer requests an invoice
     *    without one on file (Belgian legal requirement for B2B invoices).
     * 2. Show a payment success notification after the order is processed.
     */
    async validate() {
        const order = this.currentOrder;
        const partner = order.get_partner?.() ?? order.partner_id;

        if (order.is_to_invoice() && partner && !partner.is_company && !partner.parent_id) {
            if (!(partner.vat || "").trim()) {
                const vatNumber = await this._kassaPromptVatNumber(partner);
                if (vatNumber === null) {
                    order.set_to_invoice(false);
                    this.env.services.notification.add(
                        _t("Factuur geannuleerd."),
                        { type: "info", sticky: false }
                    );
                    return;
                }
            }
        }

        await super.validate(...arguments);
        if (order?.finalized) {
            this.env.services.notification.add(
                _t("Betaling verwerkt."),
                { type: "success", sticky: false }
            );
        }
    },

});

// ── PartnerList patch — sort recently-scanned partners to the top ─────────────

patch(PartnerListScreen.prototype, {
    /**
     * Override partners getter to sort recently-scanned (QR / bus event) partners
     * to the top of the list so cashiers can find them immediately after deselect.
     * Falls back to super cleanly if the base class changes its API.
     */
    get partners() {
        const all = super.partners;
        const scanned = this.pos?._kassaScannedPartnerIds;
        if (!scanned?.size) {
            return all;
        }
        const scannedParties = [];
        const otherParties = [];
        for (const p of all) {
            (scanned.has(p.id) ? scannedParties : otherParties).push(p);
        }
        return [...scannedParties, ...otherParties];
    },
});

// ── PartnerLine patch ─────────────────────────────────────────────────────────

patch(PartnerLine.prototype, {
    /** True when this partner was recently scanned via QR or updated via bus. */
    get kassaIsRecentlyScanned() {
        const pos = this.pos ?? this.env.pos;
        return pos?._kassaScannedPartnerIds?.has(this.props.partner?.id) ?? false;
    },

    /** True when the partner has an outstanding registration amount. */
    get kassaHasOutstanding() {
        return (this.props.partner.x_outstanding_amount || 0) > 0;
    },

    /** Formatted outstanding amount string, e.g. "25.00". */
    get kassaOutstandingAmount() {
        return (this.props.partner.x_outstanding_amount || 0).toFixed(2);
    },

    /** Raw payment_status value ("unpaid" | "paid" | ""). */
    get kassaPaymentStatus() {
        return this.props.partner.x_payment_status || "";
    },

    /** All session titles for display in the partner list (parsed from JSON or plain string). */
    get kassaSessionTitles() {
        return _parseSessionTitles(this.props.partner.x_session_title);
    },

    /** True when the partner has a positive wallet balance. */
    get kassaHasWallet() {
        return (this.props.partner.x_wallet_balance || 0) > 0;
    },

    /** Formatted wallet balance string, e.g. "12.50". */
    get kassaWalletBalance() {
        return (this.props.partner.x_wallet_balance || 0).toFixed(2);
    },
});

console.log("[Kassa] POS Custom module loaded successfully.");
