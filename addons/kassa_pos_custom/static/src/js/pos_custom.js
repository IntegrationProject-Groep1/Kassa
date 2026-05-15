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
import { effect } from "@odoo/owl";

/** Bus channel published by pos.order.send_partner_bus_event. */
const KASSA_BUS_CHANNEL = "kassa_partner_update";

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
        this._subscribeKassaBusEvents();
        this._watchKassaPartnerSelection();
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
            console.log("[Kassa] Partner updated from bus event:", partnerId);
        } catch (err) {
            console.error("[Kassa] Error fetching partner", partnerId, err);
        }
    },
});

// ── PaymentScreen patch ───────────────────────────────────────────────────────

/**
 * - Company customer selected → auto-enable Invoice + add Customer Account.
 * - Selecting "Customer Account" manually → auto-enables Invoice.
 * - Story 19: Badge Wallet hidden via template t-if; safety net in addNewPaymentLine.
 */
patch(PaymentScreen.prototype, {
    _kassaFindPm(name) {
        return (
            this.pos.models?.["pos.payment.method"]?.getAll?.() ||
            this.pos.payment_methods || []
        ).find((m) => m.name === name);
    },

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

    setup() {
        super.setup(...arguments);
        try {
            this._kassaActivateCompanyFlow();
        } catch (err) {
            console.warn("[Kassa] Could not auto-activate company flow on entry:", err);
        }
    },

    async selectPartner() {
        await super.selectPartner(...arguments);
        try {
            this._kassaActivateCompanyFlow();
        } catch (err) {
            console.warn("[Kassa] Could not auto-activate company flow after partner select:", err);
        }
    },

    addNewPaymentLine(paymentMethod) {
        if (paymentMethod?.name === "Badge Wallet") {
            const partner = this.currentOrder.get_partner();
            if (!partner) {
                console.warn("[Kassa] Badge Wallet geblokkeerd: geen klant geselecteerd.");
                return;
            }
            // Require a confirmed lease (x_lease_id non-empty) so we don't process
            // a payment before the CRM has responded to the wallet_lease_request.
            if (!partner.x_lease_active || !partner.x_lease_id) {
                console.warn("[Kassa] Badge Wallet geblokkeerd: wallet-lease nog niet bevestigd door CRM.");
                return;
            }
            const balanceCents = Math.round((partner.x_wallet_balance ?? 0) * 100);
            const dueCents = Math.round(this.currentOrder.get_due() * 100);
            if (balanceCents < dueCents) {
                console.warn(
                    "[Kassa] Badge Wallet geblokkeerd: onvoldoende saldo (€%s < €%s).",
                    (partner.x_wallet_balance ?? 0).toFixed(2),
                    this.currentOrder.get_due().toFixed(2)
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

});

// ── PartnerLine patch ─────────────────────────────────────────────────────────

patch(PartnerLine.prototype, {
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

    /**
     * True only when the CRM has confirmed the wallet lease (x_lease_id non-empty).
     * Prevents showing a stale €0.00 balance during the gap between QR scan and
     * wallet_lease_grant arriving from the CRM.
     */
    get kassaHasWallet() {
        return !!(this.props.partner.x_lease_active && this.props.partner.x_lease_id);
    },

    /** Formatted wallet balance string, e.g. "12.50". */
    get kassaWalletBalance() {
        return (this.props.partner.x_wallet_balance || 0).toFixed(2);
    },
});

console.log("[Kassa] POS Custom module loaded successfully.");
