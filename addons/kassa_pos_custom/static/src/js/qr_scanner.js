/** @odoo-module **/

/**
 * qr_scanner.js — QR / badge scan entry point for the Kassa POS.
 *
 * Adds a "Scan QR" button to the ProductScreen toolbar.  When pressed, the
 * browser camera opens in a full-screen overlay and continuously scans for a
 * QR code using the native BarcodeDetector API (Chrome / Android) or the
 * jsQR library as a fallback.
 *
 * On a successful scan the code is POSTed to /kassa/qr_scan (controllers/main.py),
 * which looks up or creates the Odoo partner, synchronises sessions via a
 * RabbitMQ RPC to Frontend, and fires a wallet_lease_request to CRM.
 *
 * The QR payload can be either:
 *   - a plain UUID string (identity_uuid)
 *   - a JSON object: { "identity_uuid": "...", "email": "..." }
 */

import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

/** Milliseconds between successive frames decoded in the scan loop. */
const SCAN_INTERVAL_MS = 200;

/**
 * Partner fields loaded via ORM after a successful scan.
 * Mirrors KASSA_PARTNER_FIELDS in pos_custom.js — keep in sync.
 */
const QR_PARTNER_FIELDS = [
    "id", "name", "street", "city", "state_id", "country_id",
    "email", "phone", "mobile", "barcode", "vat",
    "is_company", "parent_id", "customer_rank", "active_lang_count",
    "x_wallet_balance", "x_user_id", "x_badge_id",
    "x_outstanding_amount", "x_payment_status", "x_lease_active", "x_lease_id", "x_session_title",
];

/**
 * OWL component that renders the "Scan QR" button on the ProductScreen toolbar.
 *
 * Lifecycle:
 *   onMounted  — moves the overlay <div> to document.body so it can cover the
 *                entire viewport regardless of CSS stacking context.
 *   onWillUnmount — stops the camera stream and removes the overlay from the DOM.
 *
 * State machine (this.state.phase):
 *   "starting"    — camera permission requested, getUserMedia not yet resolved
 *   "scanning"    — camera active, scan loop running, waiting for a QR code
 *   "processing"  — QR detected, /kassa/qr_scan call in flight
 *   "error"       — unrecoverable error; message shown to cashier
 */
export class QrScanButton extends Component {
    static template = "kassa_pos_custom.QrScanButton";
    static props = {};

    /**
     * OWL setup hook — runs once before first render.
     *
     * Injects POS/ORM/RPC/notification services, creates camera and overlay refs,
     * initialises reactive state and private camera fields, and registers
     * mount/unmount handlers that manage the overlay DOM node lifecycle.
     */
    setup() {
        this.pos          = useService("pos");
        this.orm          = useService("orm");
        this.rpc          = useService("rpc");
        this.notification = useService("notification");
        this.videoRef     = useRef("video");
        this.overlayRef   = useRef("overlay");

        this.state = useState({
            open:    false,
            phase:   "starting",   // starting | scanning | processing | error
            message: "",
        });

        this._stream   = null;
        this._scanning = false;
        this._canvas   = document.createElement("canvas");
        this._ctx      = this._canvas.getContext("2d");

        onMounted(() => {
            const el = this.overlayRef.el;
            if (el) document.body.appendChild(el);
        });

        onWillUnmount(() => {
            this._stopCamera();
            const el = this.overlayRef.el;
            if (el && el.parentNode) el.parentNode.removeChild(el);
        });
    }

    // ── Public ────────────────────────────────────────────────────────────────

    /**
     * Open the QR-scan overlay and start the camera.
     *
     * The 50 ms setTimeout gives OWL one render cycle to paint the <video>
     * element into the DOM before _startCamera() tries to attach a MediaStream
     * to it.  Without this delay videoRef.el would still be null.
     */
    openScanner() {
        this.state.open    = true;
        this.state.phase   = "starting";
        this.state.message = "Camera starten...";
        // Allow the DOM to paint the <video> element before we attach the stream.
        setTimeout(() => this._startCamera(), 50);
    }

    /**
     * Close the overlay without processing a scan.
     * Stops the camera stream first to release the hardware resource immediately.
     */
    cancel() {
        this._stopCamera();
        this.state.open = false;
    }

    // ── Camera ────────────────────────────────────────────────────────────────

    /**
     * Request camera access and begin streaming to the <video> element.
     *
     * Requests the rear-facing camera (facingMode: "environment") at 1280 px
     * width so barcodes are readable on mobile without zooming.
     * On success: sets phase="scanning" and starts the scan loop.
     * On failure (permissions denied, no camera): calls _setError().
     */
    async _startCamera() {
        const video = this.videoRef.el;
        if (!video) {
            this._setError("Video element niet gevonden.");
            return;
        }
        try {
            this._stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: "environment", width: { ideal: 1280 } },
            });
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

    /**
     * Continuous frame-decode loop that runs while this._scanning === true.
     *
     * Decoder priority:
     *   1. window.BarcodeDetector (Chrome 83+, HTTPS required) — hardware-accelerated,
     *      processes the <video> element directly without canvas round-trip.
     *   2. window.jsQR (loaded via <script> tag in the QWeb template as a fallback
     *      for Firefox and Safari) — pure-JS decoder that reads RGBA pixel data from
     *      a hidden canvas.
     *
     * Per-frame errors (e.g. the video frame is not yet ready) are swallowed and
     * the loop retries after SCAN_INTERVAL_MS — they are expected during startup.
     * The loop exits as soon as a QR value is decoded.
     */
    async _runScanLoop() {
        // Prefer the native BarcodeDetector (Chrome/HTTPS); fall back to jsQR.
        const detector = window.BarcodeDetector
            ? new BarcodeDetector({ formats: ["qr_code"] })
            : null;

        if (!detector && !window.jsQR) {
            this._setError("QR-scannen wordt niet ondersteund door deze browser.");
            return;
        }

        while (this._scanning) {
            try {
                const video = this.videoRef.el;
                if (video && video.readyState >= video.HAVE_ENOUGH_DATA) {
                    let rawValue = null;

                    if (detector) {
                        const codes = await detector.detect(video);
                        if (codes.length > 0) rawValue = codes[0].rawValue;
                    } else if (window.jsQR) {
                        if (this._canvas.width !== video.videoWidth || this._canvas.height !== video.videoHeight) {
                            this._canvas.width  = video.videoWidth;
                            this._canvas.height = video.videoHeight;
                        }
                        this._ctx.drawImage(video, 0, 0, this._canvas.width, this._canvas.height);
                        const imgData = this._ctx.getImageData(0, 0, this._canvas.width, this._canvas.height);
                        const result  = window.jsQR(imgData.data, imgData.width, imgData.height);
                        if (result) rawValue = result.data;
                    }

                    if (rawValue !== null) {
                        this._scanning = false;
                        await this._onQrDetected(rawValue.trim());
                        return;
                    }
                }
            } catch (_) {
                // per-frame errors are normal; keep looping
            }
            await new Promise((r) => setTimeout(r, SCAN_INTERVAL_MS));
        }
    }

    /**
     * Stop the camera and release the hardware resource.
     * Calling this is idempotent — safe to call multiple times.
     * Each MediaStreamTrack must be stopped individually; simply dropping
     * the stream reference is not enough to turn off the camera indicator light.
     */
    _stopCamera() {
        this._scanning = false;
        if (this._stream) {
            this._stream.getTracks().forEach((t) => t.stop());
            this._stream = null;
        }
    }

    // ── QR detected ──────────────────────────────────────────────────────────

    /**
     * Handle a successfully decoded QR value.
     *
     * Payload parsing:
     *   JSON object  → extracts identity_uuid (required) and email (optional).
     *   Plain string → treated as identity_uuid directly (legacy / badge format).
     *
     * Processing flow:
     *   1. POST to /kassa/qr_scan → returns { status, partner_id, sessions }.
     *   2. Load the full partner record from Odoo via ORM.
     *   3. Upsert the partner into the POS in-memory store (Odoo 17 model API
     *      or legacy partners array, whichever is present).
     *   4. Set the partner on the current order; auto-enable invoice for companies.
     *   5. Show a success notification with wallet and session info.
     *
     * @param {string} rawValue — raw string decoded from the QR image
     */
    async _onQrDetected(rawValue) {
        this._stopCamera();
        this.state.phase   = "processing";
        this.state.message = "QR-code herkend, klant opzoeken...";

        let identityUuid = rawValue;
        let qrEmail = null;
        try {
            const parsed = JSON.parse(rawValue);
            if (parsed.identity_uuid) {
                identityUuid = parsed.identity_uuid;
                qrEmail = parsed.email || null;
            }
        } catch {
            // Plain UUID — use as-is
        }

        try {
            const result = await this._callQrScanEndpoint(identityUuid, qrEmail);

            if (!result || result.status === "error") {
                this._setError(result?.message || "Onbekende fout bij het opzoeken van de klant.");
                return;
            }

            const partnerId = result.partner_id;
            const [partner] = await this.orm.read("res.partner", [partnerId], QR_PARTNER_FIELDS);
            if (!partner) {
                this._setError("Partner kon niet worden opgehaald uit Odoo.");
                return;
            }

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

            const order = this.pos.selectedOrder;
            if (order) {
                const posPartner = this.pos.partners.find((p) => p.id === partnerId);
                if (order.set_partner) {
                    order.set_partner(posPartner || partner);
                } else {
                    order.partner_id = posPartner || partner;
                }

                if (partner.is_company || partner.parent_id) {
                    try {
                        if (order.set_to_invoice) {
                            order.set_to_invoice(true);
                        } else {
                            order.to_invoice = true;
                        }
                    } catch (err) {
                        console.warn("[Kassa] Could not auto-enable invoice for company partner:", err);
                    }
                }
            }

            this.state.open = false;

            const balance = partner.x_wallet_balance || 0;
            const leaseNote =
                result.status === "lease_requested" || result.status === "not_found_and_created"
                    ? " — saldo wordt opgehaald bij CRM"
                    : result.status === "already_active"
                    ? ` — saldo: ${this.pos.format_currency(balance)}`
                    : "";

            const sessionTitles = (result.sessions || []).map((s) => s.title).filter(Boolean);
            const sessionNote   = sessionTitles.length > 0 ? ` — ${sessionTitles.join(", ")}` : "";
            const emailNote     = qrEmail ? ` (${qrEmail})` : "";

            this.notification.add(
                `Klant geïdentificeerd: ${partner.name}${emailNote}${sessionNote}${leaseNote}`,
                { type: "success", sticky: false }
            );
        } catch (err) {
            this._setError(`Fout: ${err.message}`);
        }
    }

    /**
     * POST identity_uuid (and optionally email) to the /kassa/qr_scan controller.
     *
     * Returns the JSON response on success, or null if the call throws (network
     * error, Odoo 500, etc.).  Callers check for null / result.status === "error".
     *
     * @param {string} identityUuid — x_user_id / identity UUID from the QR code
     * @param {string|null} email   — email extracted from a JSON QR payload
     * @returns {Object|null}
     */
    async _callQrScanEndpoint(identityUuid, email) {
        try {
            const payload = { identity_uuid: identityUuid };
            if (email) payload.email = email;
            return await this.rpc("/kassa/qr_scan", payload);
        } catch (err) {
            console.error("[Kassa QR] /kassa/qr_scan call failed:", err);
            return null;
        }
    }

    /**
     * Transition the component to the error state and display a message.
     * Also stops the camera so the indicator light turns off immediately.
     *
     * @param {string} message — Dutch error string shown in the overlay
     */
    _setError(message) {
        this._stopCamera();
        this.state.phase   = "error";
        this.state.message = message;
    }
}

ProductScreen.addControlButton({
    component: QrScanButton,
    condition: () => true,
});

console.log("[Kassa] QR Scanner module loaded.");
