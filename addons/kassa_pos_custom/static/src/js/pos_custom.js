/** @odoo-module **/

/**
 * Kassa POS Custom — Story 9 & 21
 *
 * 1. Patches PosStore to subscribe to "kassa_partner_update" bus events.
 *    On event: fetches only that one partner via RPC and upserts it into the
 *    local partners list — no full reload, no transaction interruption.
 *
 * 2. Registers a reactive OWL effect that fires whenever the current order's
 *    partner changes.  If x_outstanding_amount > 0 the generic "Inschrijving"
 *    product is automatically added to the order at the outstanding price.
 *
 * 3. Patches PartnerLine to expose getters used by the XML template to render
 *    the outstanding-amount badge.
 */

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { PartnerLine } from "@point_of_sale/app/screens/partner_list/partner_line";
import { effect } from "@odoo/owl";

/** Bus channel published by pos.order.send_partner_bus_event. */
const KASSA_BUS_CHANNEL = "kassa_partner_update";

/** Name of the generic registration fee product that must exist in Odoo. */
const INSCHRIJVING_PRODUCT_NAME = "Inschrijving";

/** Fields fetched for a single partner on a granular bus-event update. */
const KASSA_PARTNER_FIELDS = [
    "id", "name", "street", "city", "state_id", "country_id",
    "email", "phone", "mobile", "barcode", "vat",
    "is_company", "parent_id", "customer_rank", "active_lang_count",
    "x_wallet_balance", "x_user_id", "x_badge_id",
    "x_outstanding_amount", "x_payment_status",
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
                    this._kassaAddInschrijvingProduct(order, partner);
                }
            });
        } catch (err) {
            console.warn("[Kassa] Could not register partner-watch effect:", err);
        }
    },

    /**
     * Adds a single "Inschrijving" orderline to the given order with the
     * partner's outstanding amount as the unit price.
     *
     * Guards:
     *   - Product not found → warn and bail (cashier must create it in Odoo).
     *   - Line already present → skip (idempotent; safe for effect re-runs).
     */
    _kassaAddInschrijvingProduct(order, partner) {
        try {
            // Search the POS product catalog.  Odoo 17 exposes products via
            // this.models['product.product'] (new service) or this.products (legacy).
            const allProducts =
                this.models?.["product.product"]?.getAll?.() ||
                this.products ||
                [];

            const product = allProducts.find(
                (p) =>
                    p.name === INSCHRIJVING_PRODUCT_NAME ||
                    p.display_name === INSCHRIJVING_PRODUCT_NAME
            );

            if (!product) {
                console.warn(
                    "[Kassa] Product '%s' not found in POS catalog. " +
                        "Create it in Odoo (service type, available_in_pos=True).",
                    INSCHRIJVING_PRODUCT_NAME
                );
                return;
            }

            // Do not add a duplicate line if the product is already in the order.
            const lines =
                order.get_orderlines ? order.get_orderlines() : order.orderlines || [];
            const alreadyPresent = lines.some((l) => {
                const p = l.get_product ? l.get_product() : l.product;
                return p && p.id === product.id;
            });
            if (alreadyPresent) return;

            // add_product with a custom price so the cashier does not need to
            // type anything — the outstanding amount is pre-filled.
            order.add_product(product, { price: partner.x_outstanding_amount });

            console.log(
                "[Kassa] Auto-added '%s' line: €%s for partner_id=%s",
                INSCHRIJVING_PRODUCT_NAME,
                partner.x_outstanding_amount,
                partner.id
            );
        } catch (err) {
            console.error("[Kassa] Error adding Inschrijving product:", err);
        }
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
            const idx = this.partners.findIndex((p) => p.id === partnerId);
            if (idx !== -1) {
                Object.assign(this.partners[idx], updated);
            } else {
                this.partners.push(updated);
            }
            console.log("[Kassa] Partner updated from bus event:", partnerId);
        } catch (err) {
            console.error("[Kassa] Error fetching partner", partnerId, err);
        }
    },
});

// ── PaymentScreen patch ───────────────────────────────────────────────────────

/**
 * Two-way convenience link between "Customer Account" and the Invoice toggle:
 *
 *   1. Selecting "Customer Account" on the left  → auto-enables Invoice.
 *   2. Enabling the Invoice toggle on the right  → auto-adds "Customer Account"
 *      as the payment method (only when no payment line exists yet, so the
 *      cashier can still swap it to Cash/Card for customers who want an invoice
 *      but pay directly).
 */
patch(PaymentScreen.prototype, {
    addNewPaymentLine(paymentMethod) {
        const result = super.addNewPaymentLine(...arguments);
        try {
            if (paymentMethod?.name === "Customer Account") {
                const order = this.currentOrder;
                if (order && !order.to_invoice) {
                    if (order.set_to_invoice) {
                        order.set_to_invoice(true);
                    } else {
                        order.to_invoice = true;
                    }
                    console.log("[Kassa] Auto-enabled Invoice for Customer Account.");
                }
            }
        } catch (err) {
            console.warn("[Kassa] Could not auto-enable invoice:", err);
        }
        return result;
    },

    toggleIsToInvoice() {
        super.toggleIsToInvoice(...arguments);
        try {
            const order = this.currentOrder;
            if (!order || !order.to_invoice) return;

            // Only auto-add when no payment line has been chosen yet.
            const lines = order.paymentlines || order.payment_ids || [];
            if (lines.length > 0) return;

            const pm = (
                this.pos.models?.["pos.payment.method"]?.getAll?.() ||
                this.pos.payment_methods ||
                []
            ).find((m) => m.name === "Customer Account");

            if (pm) {
                this.addNewPaymentLine(pm);
                console.log("[Kassa] Auto-added Customer Account for Invoice.");
            }
        } catch (err) {
            console.warn("[Kassa] Could not auto-add Customer Account:", err);
        }
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
});

console.log("[Kassa] POS Custom module loaded successfully.");
