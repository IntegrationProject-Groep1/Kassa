/** @odoo-module **/

/**
 * Kassa POS Custom — Story 9 & 21
 *
 * 1. Patches PosStore to subscribe to KASSA_PARTNER_UPDATE bus notifications
 *    (sent via session._notify() on the authorized POS session channel).
 *    On event: fetches only that one partner via RPC, upserts it into the
 *    local partners list, and directly triggers session product auto-add.
 *
 * 2. Registers a reactive OWL effect that fires whenever the current order's
 *    partner changes.  If x_session_title is set,
 *    the session-specific product is automatically added to the order at the
 *    outstanding price.  Without a session title no product is auto-added
 *    (cashier handles manually; outstanding-amount badge is still visible).
 *
 * 3. Patches PartnerLine to expose getters used by the XML template to render
 *    the outstanding-amount badge and the session title.
 */

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { PartnerLine } from "@point_of_sale/app/screens/partner_list/partner_line/partner_line";
import { PartnerListScreen } from "@point_of_sale/app/screens/partner_list/partner_list";
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { sprintf } from "@web/core/utils/strings";

/** Notification type sent by pos.order.send_partner_bus_event via session._notify(). */
const KASSA_PARTNER_NOTIFICATION = "KASSA_PARTNER_UPDATE";

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
    },

    /**
     * Register a partner ID as "recently scanned via QR or bus update".
     * PartnerList uses this set to sort these partners to the top of the list.
     */
    kassaRegisterScannedPartner(id) {
        if (id) this._kassaScannedPartnerIds.add(id);
    },

    /**
     * Subscribe to the KASSA_PARTNER_UPDATE notification type.
     *
     * In Odoo 17, bus.bus._sendone() with a plain string channel is silently
     * rejected by the server's bus security model for non-whitelisted channels.
     * The Python side now uses session._notify('KASSA_PARTNER_UPDATE', ...) which
     * goes through the POS session's own authorized WebSocket channel
     * ('pos.session', session_id).  The POS core already subscribes to that
     * channel at startup, so we only need bus_service.subscribe() — no addChannel().
     */
    _subscribeKassaBusEvents() {
        try {
            this.env.services.bus_service.subscribe(
                KASSA_PARTNER_NOTIFICATION,
                (payload) => {
                    this._onKassaPartnerUpdate(payload).catch((err) =>
                        console.error("[Kassa] Bus handler error:", err)
                    );
                }
            );
            // Load products from SYNC_PRODUCT_UPDATED into this.db so the 1.5s
            // wait in _kassaAddSessionProducts can find them without a fallback RPC.
            this.env.services.bus_service.subscribe(
                "SYNC_PRODUCT_UPDATED",
                (payload) => {
                    const products = payload?.["product.product"];
                    const count = Array.isArray(products) ? products.length : 0;
                    console.log("[Kassa] SYNC_PRODUCT_UPDATED ontvangen: %d product(en)", count);
                    if (count && typeof this._loadProductProduct === "function") {
                        try {
                            this._loadProductProduct(products);
                        } catch (err) {
                            console.warn("[Kassa] SYNC_PRODUCT_UPDATED load error:", err);
                        }
                    }
                }
            );
            // Remove deleted session product from tiles and open orders.
            this.env.services.bus_service.subscribe(
                "SYNC_SESSION_DELETED",
                (payload) => {
                    const session_id = payload?.session_id;
                    if (!session_id) return;
                    console.log("[Kassa] SYNC_SESSION_DELETED ontvangen:", session_id);
                    this._onKassaSessionDeleted(session_id);
                }
            );
            this.env.services.bus_service.start();
        } catch (err) {
            console.warn("[Kassa] Could not subscribe to bus_service:", err);
        }
    },

    /**
     * Orchestrator: ensures all session products are in the POS db, then adds
     * one order line per registered session.  Idempotent — existing lines are
     * skipped or price-updated rather than duplicated.
     *
     * Flow:
     *  1. Parse session entries from x_session_title JSON (with individual prices).
     *  2. Detect which products are missing from this.db.product_by_id.
     *  3. If any missing: wait 1.5 s for a SYNC_PRODUCT_UPDATED bus event.
     *  4. For still-missing products: call /kassa/load_session_products which
     *     creates them in Odoo (if needed) and returns the product data so we
     *     can insert them directly into this.db via this._loadProductProduct().
     *  5. Add/update order lines.
     */
    async _kassaAddSessionProducts(order, partner) {
        console.log(
            "[Kassa] _kassaAddSessionProducts — partner:", partner?.name,
            "| sessions:", partner?.x_session_title,
            "| outstanding:", partner?.x_outstanding_amount
        );

        // Parse entries, preserving individual prices from Planning.
        let entries = [];
        const raw = partner.x_session_title;
        if (raw) {
            try {
                const parsed = JSON.parse(raw);
                if (Array.isArray(parsed)) {
                    entries = parsed
                        .map((e) =>
                            typeof e === "object" && e !== null
                                ? { title: e.title || "", price: e.price ?? null, session_id: e.session_id || null }
                                : { title: String(e), price: null, session_id: null }
                        )
                        .filter((e) => e.title);
                } else {
                    entries = [{ title: String(parsed), price: null }];
                }
            } catch {
                entries = [{ title: raw, price: null }];
            }
        }

        if (!entries.length) {
            console.warn("[Kassa] Geen sessietitels op partner %s.", partner.id);
            return;
        }

        const _find = (title, session_id = null) => {
            // Merge legacy PosDB and Odoo 17 reactive model store (deduplicated by id).
            const byDb = Object.values(this.db?.product_by_id || {});
            const byModel = this.models?.["product.product"]?.getAll?.() || [];
            const dbIds = new Set(byDb.map((p) => p.id));
            const all = [...byDb, ...byModel.filter((p) => !dbIds.has(p.id))];
            // Primary: stable Planning session_id (survives title renames).
            if (session_id) {
                const bySessionId = all.find((p) => p.x_session_id === session_id);
                if (bySessionId) return bySessionId;
            }
            // Fallback: exact name match.
            return all.find((p) => p.name === title || p.display_name === title);
        };

        // Step 2: determine which are missing upfront
        let missingEntries = entries.filter((e) => !_find(e.title, e.session_id));

        // Step 3: single shared wait for SYNC_PRODUCT_UPDATED (avoids N × timeout)
        if (missingEntries.length) {
            console.log("[Kassa] Wachten op SYNC_PRODUCT_UPDATED voor:", missingEntries.map((e) => e.title));
            await new Promise((r) => setTimeout(r, 1500));
            missingEntries = missingEntries.filter((e) => !_find(e.title, e.session_id));
        }

        // Step 4: synchronous server fallback — create + return product data
        if (missingEntries.length) {
            console.log("[Kassa] Direct laden vanuit Odoo:", missingEntries.map((e) => e.title));
            await this._kassaLoadMissingProducts(missingEntries);
            const stillMissing = missingEntries.filter((e) => !_find(e.title, e.session_id));
            if (stillMissing.length) {
                console.warn("[Kassa] Kon producten niet laden:", stillMissing.map((e) => e.title));
            }
        }

        // Step 5: compute prices and add/update order lines.
        // A session entry with price===0 (explicitly zero from Planning, not null) is
        // treated the same as null — it means "no known price" so the distribution
        // algorithm can share the outstanding amount across all unpriced sessions.
        // Only a positive price from Planning counts as a "known" price.
        const totalOutstanding = partner.x_outstanding_amount || 0;
        const hasKnownPrice = (e) => e.price !== null && e.price > 0;
        const sumKnownCents = entries.reduce(
            (s, e) => s + (hasKnownPrice(e) ? Math.round(e.price * 100) : 0), 0
        );
        const nullCount = entries.filter((e) => !hasKnownPrice(e)).length;
        const remainingCents = Math.max(0, Math.round(totalOutstanding * 100) - sumKnownCents);
        const basePerNull = nullCount > 0 ? Math.floor(remainingCents / nullCount) : 0;
        let leftoverCents = nullCount > 0 ? remainingCents - basePerNull * nullCount : 0;

        const lines = order.get_orderlines ? order.get_orderlines() : order.orderlines || [];

        for (const entry of entries) {
            const product = _find(entry.title, entry.session_id);
            if (!product) continue;

            let priceCents;
            if (hasKnownPrice(entry)) {
                priceCents = Math.round(entry.price * 100);
            } else if (nullCount > 0 && totalOutstanding > 0) {
                // Distribute remaining outstanding evenly across unpriced sessions.
                priceCents = basePerNull + (leftoverCents > 0 ? 1 : 0);
                if (leftoverCents > 0) leftoverCents--;
            } else {
                // No outstanding amount — fall back to the product's catalogue price.
                const listPrice = product.lst_price ?? product.list_price ?? 0;
                priceCents = Math.round(listPrice * 100);
            }
            const price = priceCents / 100;

            const existingLine = lines.find((l) => {
                const p = l.get_product ? l.get_product() : l.product;
                return p && p.id === product.id;
            });

            if (existingLine) {
                const current = existingLine.get_unit_price
                    ? existingLine.get_unit_price()
                    : existingLine.price;
                if (Math.round((current || 0) * 100) !== Math.round(price * 100)) {
                    if (existingLine.set_unit_price) existingLine.set_unit_price(price);
                    else existingLine.price = price;
                    console.log("[Kassa] Prijs bijgewerkt '%s': €%s", entry.title, price.toFixed(2));
                }
            } else {
                order.add_product(product, { price });
                console.log("[Kassa] Auto-added '%s': €%s", entry.title, price.toFixed(2));
            }
        }
    },

    /**
     * Fetches missing session products from Odoo via /kassa/load_session_products.
     * The endpoint creates products that don't exist yet (idempotent) and returns
     * their full POS field set.  We then call this._loadProductProduct() which is
     * the same internal method used by the POS startup loader — it wraps each
     * product dict in a proper Product class instance and adds it to this.db.
     */
    async _kassaLoadMissingProducts(entries) {
        try {
            const result = await this.env.services.rpc(
                "/kassa/load_session_products", { sessions: entries }
            );
            const products = result?.products || [];
            if (!products.length) return;

            if (typeof this._loadProductProduct === "function") {
                this._loadProductProduct(products);
                console.log("[Kassa] %d product(en) geladen via _loadProductProduct.", products.length);
            } else {
                // Fallback: insert raw data; product will lack class methods but is findable.
                for (const p of products) {
                    p.pos = this;
                    p.env = this.env;
                    p.applicablePricelistItems = {};
                    this.db.product_by_id[p.id] = p;
                }
                console.log("[Kassa] %d product(en) rechtstreeks in db ingevoegd.", products.length);
            }
        } catch (err) {
            console.warn("[Kassa] _kassaLoadMissingProducts mislukt:", err);
        }
    },

    /**
     * Triggered by a KASSA_PARTNER_UPDATE bus notification from send_partner_bus_event.
     * Fetches only the affected partner via a targeted RPC call, upserts it into
     * the local in-memory partners list, then directly triggers session product
     * auto-add if the updated partner is on the current order.
     *
     * Directly calling _kassaAddSessionProducts here avoids relying on the OWL
     * effect re-firing, which is fragile when insert() creates a new reactive proxy
     * or when effect() is registered outside a component setup context.
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
            let posPartner;
            if (this.models?.["res.partner"]?.insert) {
                posPartner = this.models["res.partner"].insert(updated);
            } else {
                const idx = this.partners.findIndex((p) => p.id === partnerId);
                if (idx !== -1) {
                    Object.assign(this.partners[idx], updated);
                    posPartner = this.partners[idx];
                } else {
                    this.partners.push(updated);
                    posPartner = updated;
                }
            }
            this.kassaRegisterScannedPartner(partnerId);
            console.log("[Kassa] Partner updated from bus event:", partnerId);

            // Directly trigger session product auto-add instead of relying on the
            // OWL effect, which may not re-fire if insert() creates a new proxy.
            if (this.config?.name === "Inschrijvingskassa") {
                const order = this.selectedOrder;
                const orderPartnerId =
                    order?.partner_id?.id ?? order?.partner_id ??
                    order?.get_partner?.()?.id;
                if (order && orderPartnerId === partnerId && updated.x_session_title) {
                    await this._kassaAddSessionProducts(order, posPartner || updated);
                }
            }
        } catch (err) {
            console.error("[Kassa] Error fetching partner", partnerId, err);
        }
    },

    /**
     * Handle SYNC_SESSION_DELETED bus event.
     *
     * Removes the deleted session product from the reactive model store and the
     * legacy PosDB so the product tile disappears immediately.  Also removes any
     * open order lines for this product from the current order, then shows a
     * warning notification to the cashier.
     */
    _onKassaSessionDeleted(session_id) {
        // Product tile removal is handled by the built-in SYNC_PRODUCT_UPDATED
        // mechanism: the server also calls kassa_notify_product_update after
        // marking the product available_in_pos=False.  updateModelsData() diffs
        // the incoming list against db.product_by_id and calls remove_products()
        // for any product no longer present — so we don't need to touch the store.
        try {
            // Find the product by its stable Planning ID (for order line cleanup).
            const byDb = Object.values(this.db?.product_by_id || {});
            const byModel = this.models?.["product.product"]?.getAll?.() || [];
            const product = [...byDb, ...byModel].find((p) => p.x_session_id === session_id);

            if (product) {
                // Remove order lines for this product from the current order.
                // Odoo 17 API: removeOrderline (camelCase).
                const order = this.selectedOrder;
                if (order) {
                    const lines = order.get_orderlines ? order.get_orderlines() : order.orderlines || [];
                    const toRemove = lines.filter((l) => {
                        const p = l.get_product ? l.get_product() : l.product;
                        return p && p.id === product.id;
                    });
                    for (const line of toRemove) {
                        if (typeof order.removeOrderline === "function") {
                            order.removeOrderline(line);
                        } else if (typeof order.remove_orderline === "function") {
                            order.remove_orderline(line);
                        }
                    }
                    if (toRemove.length) {
                        console.log("[Kassa] %d orderlijn(en) verwijderd voor sessie %s", toRemove.length, session_id);
                    }
                }
            }

            // Notify cashier — sticky so they don't miss it.
            try {
                this.env.services.notification.add(
                    _t("Sessie verwijderd. Controleer de bestelling."),
                    { type: "warning", sticky: true }
                );
            } catch { /* notification service may not be available */ }
        } catch (err) {
            console.error("[Kassa] _onKassaSessionDeleted fout:", err);
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

// ── WalkinEmailDialog ─────────────────────────────────────────────────────────

/**
 * Shown when a session product is tapped without a customer on the order.
 * Collects an email address, calls /kassa/register_walkin to find-or-create the
 * partner, then sets it on the order so the session sale is tracked correctly.
 */
class WalkinEmailDialog extends Component {
    static template = "kassa_pos_custom.WalkinEmailDialog";
    static components = { Dialog };
    static props = {
        productName: String,
        onConfirm: Function,
        onCancel: Function,
        close: Function,
    };

    setup() {
        this.state = useState({ email: "", error: "", loading: false });
    }

    _isValidEmail(val) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val.trim());
    }

    async confirm() {
        const email = this.state.email.trim().toLowerCase();
        if (!this._isValidEmail(email)) {
            this.state.error = _t("Ongeldig e-mailadres.");
            return;
        }
        this.state.error = "";
        this.state.loading = true;
        try {
            await this.props.onConfirm(email);
            this.props.close();
        } catch {
            this.state.loading = false;
            this.state.error = _t("Kon geen account aanmaken. Probeer opnieuw.");
        }
    }

    cancel() {
        this.props.onCancel();
        this.props.close();
    }
}

// ── ProductScreen patch ───────────────────────────────────────────────────────

/**
 * Intercept product additions to detect session products clicked without a
 * customer.  Shows WalkinEmailDialog to collect an email, find-or-create the
 * Odoo partner, and set it on the order before the product line is added.
 */
patch(ProductScreen.prototype, {
    /**
     * True when the product is a Planning session product.
     *
     * Primary check: x_session_id (loaded via _loader_params_product_product
     * override — set by receiver.py and controllers/main.py on every session product).
     * Fallback: pos_categ_ids membership in the "Sessions" POS category.
     * The fallback normalises entries as both raw IDs (integers) and objects
     * with an .id property are valid in Odoo 17's reactive model store.
     */
    _kassaIsSessionProduct(product) {
        try {
            // Primary: stable Planning ID — most reliable, no category dependency.
            if (product?.x_session_id) return true;

            // Fallback: POS category membership (handles products without x_session_id).
            const rawIds = product?.pos_categ_ids;
            if (!rawIds || !rawIds.length) return false;
            const allCateg = this.pos.models?.["pos.category"]?.getAll?.() || [];
            const sessionIds = new Set(
                allCateg.filter((c) => c.name === "Sessions").map((c) => c.id)
            );
            if (!sessionIds.size) return false;
            // Normalize: Odoo 17 may store many2many as raw ints or as objects.
            return rawIds.some((entry) => {
                const id = typeof entry === "object" && entry !== null ? entry.id : entry;
                return sessionIds.has(id);
            });
        } catch {
            return false;
        }
    },

    /**
     * Open WalkinEmailDialog and wait for the cashier to enter an email.
     * Resolves true if a partner was successfully created and set on the order,
     * false if the cashier cancelled.
     * _kassaRegisterWalkin throws on failure so the dialog can show the error.
     */
    async _kassaPromptWalkinEmail(product) {
        return new Promise((resolve) => {
            this.env.services.dialog.add(WalkinEmailDialog, {
                productName: product.display_name || product.name,
                onConfirm: async (email) => {
                    const partner = await this._kassaRegisterWalkin(email);
                    if (this.currentOrder?.set_partner) {
                        this.currentOrder.set_partner(partner);
                    } else if (this.currentOrder) {
                        this.currentOrder.partner_id = partner;
                    }
                    this.pos.kassaRegisterScannedPartner?.(partner.id);
                    // Auto-add existing sessions for returning visitors.
                    if (partner.x_session_title) {
                        this.pos._kassaAddSessionProducts(this.currentOrder, partner).catch((e) =>
                            console.warn("[Kassa] Walk-in _kassaAddSessionProducts:", e)
                        );
                    }
                    resolve(true);
                    // WalkinEmailDialog.confirm() calls this.props.close() after this returns
                },
                onCancel: () => resolve(false),
            });
        });
    },

    /**
     * Call /kassa/register_walkin, load the full partner record, insert it into
     * the POS store, and return the POS partner object.
     * Throws so the dialog can display the error and stay open for retry.
     */
    async _kassaRegisterWalkin(email) {
        const result = await this.env.services.rpc("/kassa/register_walkin", { email });
        if (!result || result.status === "error") {
            throw new Error(result?.message || "registration failed");
        }
        const [partner] = await this.env.services.orm.read(
            "res.partner", [result.partner_id], KASSA_PARTNER_FIELDS
        );
        if (!partner) throw new Error("partner read failed");
        if (this.pos.models?.["res.partner"]?.insert) {
            return this.pos.models["res.partner"].insert(partner);
        }
        return partner;
    },

    /**
     * Override the core product-add handler to intercept session products when
     * no customer is on the order.  Cancelling the dialog aborts the add.
     */
    async addProductToOrder(product) {
        if (this._kassaIsSessionProduct(product) && !this.currentOrder?.get_partner?.()) {
            console.log("[Kassa] Sessieproduct zonder klant — e-maildialoog openen:", product.name);
            const ok = await this._kassaPromptWalkinEmail(product);
            if (!ok) {
                console.log("[Kassa] Walk-in registratie geannuleerd.");
                return;
            }
        }
        return super.addProductToOrder(...arguments);
    },
});

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

    /**
     * Called when the cashier confirms a partner selection from the customer tab.
     * After delegating to super (which sets the partner on the current order and
     * navigates back), directly trigger session product auto-add for the
     * Inschrijvingskassa so the cashier doesn't need to scan a QR code.
     *
     * _kassaAddSessionProducts is idempotent — already-present lines are skipped
     * — so duplicate calls from the OWL effect and this hook are safe.
     */
    // Odoo 17: confirm() takes no arguments; partner is in this.state.selectedPartner.
    async confirm() {
        const partner = this.state?.selectedPartner;
        console.log(
            "[Kassa] PartnerListScreen.confirm() — partner:", partner?.name,
            "| config:", this.pos?.config?.name,
            "| session_title:", partner?.x_session_title
        );
        await super.confirm(...arguments);
        try {
            if (
                this.pos?.config?.name === "Inschrijvingskassa" &&
                partner?.x_session_title
            ) {
                const order = this.pos.selectedOrder;
                if (order) {
                    await this.pos._kassaAddSessionProducts(order, partner);
                }
            }
        } catch (err) {
            console.error("[Kassa] Auto-add session products (customer tab) error:", err);
        }
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
