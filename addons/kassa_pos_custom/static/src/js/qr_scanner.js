/** @odoo-module **/

import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

const SCAN_INTERVAL_MS = 200;

const QR_PARTNER_FIELDS = [
    "id", "name", "street", "city", "state_id", "country_id",
    "email", "phone", "mobile", "barcode", "vat",
    "is_company", "parent_id", "customer_rank", "active_lang_count",
    "x_wallet_balance", "x_user_id", "x_badge_id",
    "x_outstanding_amount", "x_payment_status", "x_lease_active", "x_lease_id", "x_session_title",
];

export class QrScanButton extends Component {
    static template = "kassa_pos_custom.QrScanButton";
    static props = {};

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

    openScanner() {
        this.state.open    = true;
        this.state.phase   = "starting";
        this.state.message = "Camera starten...";
        // Allow the DOM to paint the <video> element before we attach the stream.
        setTimeout(() => this._startCamera(), 50);
    }

    cancel() {
        this._stopCamera();
        this.state.open = false;
    }

    // ── Camera ────────────────────────────────────────────────────────────────

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

    _stopCamera() {
        this._scanning = false;
        if (this._stream) {
            this._stream.getTracks().forEach((t) => t.stop());
            this._stream = null;
        }
    }

    // ── QR detected ──────────────────────────────────────────────────────────

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

                if (partner.parent_id) {
                    try {
                        if (order.set_to_invoice) {
                            order.set_to_invoice(true);
                        } else {
                            order.to_invoice = true;
                        }
                    } catch (err) {
                        console.warn("[Kassa] Could not auto-enable invoice for company member:", err);
                    }
                }
            }

            this.state.open = false;

            const leaseNote =
                result.status === "lease_requested" || result.status === "not_found_and_created"
                    ? " — saldo wordt opgehaald bij CRM"
                    : result.status === "already_active"
                    ? " — actief saldo beschikbaar"
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
