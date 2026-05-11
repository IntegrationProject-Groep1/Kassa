/** @odoo-module **/

/**
 * Kassa QR Scanner — Story: QR-code identification at the kassa
 *
 * Adds a "📷 Scan QR" button to the POS ProductScreen (visible at all times).
 * On click: opens the laptop camera in a modal dialog, decodes the QR code
 * (which contains the customer's identity_uuid / master UUID), looks up or
 * creates the res.partner, sets them as the current order's customer, and
 * fires a wallet_lease_request to CRM if no active lease exists yet.
 *
 * Technology: BarcodeDetector API (Chrome-native, no external library).
 * If not supported, a clear error is shown and no crash occurs.
 */

import { Component, useState, useRef, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

/** Interval between QR scan attempts (ms). */
const SCAN_INTERVAL_MS = 200;

/** Partner fields fetched after a successful QR scan (matches KASSA_PARTNER_FIELDS). */
const QR_PARTNER_FIELDS = [
    "id", "name", "street", "city", "state_id", "country_id",
    "email", "phone", "mobile", "barcode", "vat",
    "is_company", "parent_id", "customer_rank", "active_lang_count",
    "x_wallet_balance", "x_user_id", "x_badge_id",
    "x_outstanding_amount", "x_payment_status", "x_lease_active", "x_session_title",
];

// ── QrScannerModal ────────────────────────────────────────────────────────────

/**
 * Full-screen camera modal rendered by the dialog service.
 * Receives `close` prop automatically from Odoo's dialog service.
 */
export class QrScannerModal extends Component {
    static template = "kassa_pos_custom.QrScannerModal";
    static props = { close: Function };

    setup() {
        this.pos          = useService("pos");
        this.orm          = useService("orm");
        this.rpc          = useService("rpc");
        this.notification = useService("notification");
        this.videoRef     = useRef("video");

        this.state = useState({
            phase:   "starting",   // starting | scanning | processing | error
            message: "Camera starten...",
        });

        this._stream   = null;
        this._scanning = false;

        this._startCamera();
        onWillUnmount(() => this._stopCamera());
    }

    // ── Camera ────────────────────────────────────────────────────────────────

    async _startCamera() {
        if (!window.BarcodeDetector) {
            this._setError(
                "BarcodeDetector wordt niet ondersteund door deze browser. " +
                "Gebruik Google Chrome 88 of nieuwer."
            );
            return;
        }

        try {
            this._stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: "environment", width: { ideal: 1280 } },
            });
            const video = this.videoRef.el;
            video.srcObject = this._stream;
            await video.play();
            this.state.phase   = "scanning";
            this.state.message = "Houd de QR-code voor de camera...";
            this._scanning     = true;
            this._runScanLoop();
        } catch (err) {
            this._setError(`Camera niet beschikbaar: ${err.message}`);
        }
    }

    async _runScanLoop() {
        const detector = new BarcodeDetector({ formats: ["qr_code"] });
        while (this._scanning) {
            try {
                const video = this.videoRef.el;
                if (video && video.readyState >= video.HAVE_ENOUGH_DATA) {
                    const codes = await detector.detect(video);
                    if (codes.length > 0) {
                        this._scanning = false;
                        await this._onQrDetected(codes[0].rawValue.trim());
                        return;
                    }
                }
            } catch (_) {
                // per-frame detection errors are normal; keep looping
            }
            await new Promise((r) => setTimeout(r, SCAN_INTERVAL_MS));
        }
    }

    _stopCamera() {
        this._scanning = false;
        if (this._stream) {
            this._stream.getTracks().forEach((t) => t.stop());
            this._stream = null;
        }
    }

    // ── QR detected ──────────────────────────────────────────────────────────

    async _onQrDetected(uuid) {
        this._stopCamera();
        this.state.phase   = "processing";
        this.state.message = "QR-code herkend, klant opzoeken...";

        try {
            // 1. Trigger lease check + placeholder creation on the backend.
            //    The controller returns the Odoo partner_id regardless of
            //    whether the profile was already known.
            const result = await this._callQrScanEndpoint(uuid);

            if (!result || result.status === "error") {
                this._setError(result?.message || "Onbekende fout bij het opzoeken van de klant.");
                return;
            }

            const partnerId = result.partner_id;

            // 2. Fetch fresh partner data (includes the just-created placeholder
            //    if it was new, or the existing up-to-date record).
            const [partner] = await this.orm.read("res.partner", [partnerId], QR_PARTNER_FIELDS);
            if (!partner) {
                this._setError("Partner kon niet worden opgehaald uit Odoo.");
                return;
            }

            // 3. Upsert into the POS in-memory partner cache so it is immediately
            //    available without a full session reload.
            if (this.pos.models?.["res.partner"]?.insert) {
                this.pos.models["res.partner"].insert(partner);
            } else {
                const idx = this.pos.partners.findIndex((p) => p.id === partnerId);
                if (idx !== -1) {
                    Object.assign(this.pos.partners[idx], partner);
                } else {
                    this.pos.partners.push(partner);
                }
            }

            // 4. Set as the current order's customer.
            const order = this.pos.selectedOrder;
            if (order) {
                // Odoo 17 POS: set_partner is the standard Order method.
                // Use the partner from the POS cache so reactive references stay valid.
                const posPartner = this.pos.partners.find((p) => p.id === partnerId);
                if (order.set_partner) {
                    order.set_partner(posPartner || partner);
                } else {
                    // Fallback for newer Odoo builds that use direct property assignment.
                    order.partner_id = posPartner || partner;
                }
            }

            this.props.close();

            const leaseNote =
                result.status === "lease_requested" || result.status === "not_found_and_created"
                    ? " — saldo wordt opgehaald bij CRM"
                    : result.status === "already_active"
                    ? " — actief saldo beschikbaar"
                    : "";

            const sessionTitles = (result.sessions || []).map((s) => s.title).filter(Boolean);
            const sessionNote = sessionTitles.length > 0
                ? ` — ${sessionTitles.join(", ")}`
                : "";

            this.notification.add(
                `Klant geïdentificeerd: ${partner.name}${sessionNote}${leaseNote}`,
                { type: "success", sticky: false }
            );
        } catch (err) {
            this._setError(`Fout: ${err.message}`);
        }
    }

    async _callQrScanEndpoint(uuid) {
        try {
            return await this.rpc("/kassa/qr_scan", { identity_uuid: uuid });
        } catch (err) {
            console.error("[Kassa QR] /kassa/qr_scan call failed:", err);
            return null;
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    _setError(message) {
        this._stopCamera();
        this.state.phase   = "error";
        this.state.message = message;
    }

    cancel() {
        this._stopCamera();
        this.props.close();
    }
}

// ── QrScanButton ──────────────────────────────────────────────────────────────

/**
 * Small control button registered on the ProductScreen.
 * Visible at all times in every POS session that has this module installed.
 */
export class QrScanButton extends Component {
    static template = "kassa_pos_custom.QrScanButton";
    static props    = {};

    setup() {
        this.dialog = useService("dialog");
    }

    openScanner() {
        this.dialog.add(QrScannerModal, {});
    }
}

// Register on the main POS product screen (Odoo 17 control buttons API).
ProductScreen.addControlButton({
    component: QrScanButton,
    condition: () => true,
});

console.log("[Kassa] QR Scanner module loaded.");
