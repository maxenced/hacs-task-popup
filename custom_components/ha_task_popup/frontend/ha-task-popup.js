/*
 * HA Task Popup — module JS global chargé par l'intégration (add_extra_js_url).
 *
 * S'abonne à `ha_task_popup/subscribe` et affiche la première tâche active en
 * plein écran, dans le style des pop-ups Bubble Card du dashboard (voile flouté,
 * panneau « verre », boutons pilule). Les tâches suivantes s'affichent une fois
 * la précédente faite ou snoozée.
 *
 * Par défaut, le popup ne s'affiche que dans Fully Kiosk sur les tablettes
 * choisies (comparaison de `fully.getDeviceId()` avec l'appareil HA).
 * Forçage local (tests) : localStorage["ha_task_popup_show"] = "1" (toujours)
 * ou "0" (jamais).
 */

const DOMAIN = "ha_task_popup";
const TAG = "ha-task-popup-overlay";
const FORCE_KEY = "ha_task_popup_show";

const I18N = {
  fr: { done: "Fait", snooze: "Snooze", min: "min" },
  en: { done: "Done", snooze: "Snooze", min: "min" },
};

const STYLE = `
  :host {
    position: fixed;
    inset: 0;
    z-index: 10000;
    display: block;
    font-family: var(--ha-font-family-body, var(--primary-font-family, Roboto, sans-serif));
    -webkit-tap-highlight-color: transparent;
  }
  .backdrop {
    position: absolute;
    inset: 0;
    background-color: rgba(6, 9, 16, 0.42);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    animation: fade 0.25s ease-out;
  }
  .popup {
    position: absolute;
    inset: 14px;
    display: flex;
    flex-direction: column;
    box-sizing: border-box;
    padding: 18px 18px 22px;
    border-radius: 42px;
    color: var(--task-fg);
    background:
      radial-gradient(ellipse 80% 60% at 20% 0%, rgba(255, 255, 255, 0.10), transparent 65%),
      color-mix(in srgb, var(--task-color) 88%, transparent);
    border: 1px solid rgba(255, 255, 255, 0.10);
    box-shadow: 0 0 42px rgba(0, 0, 0, 0.35);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    animation: rise 0.3s cubic-bezier(0.2, 0.9, 0.3, 1.1);
    overflow: hidden;
  }
  .header {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .glass {
    background-color: rgba(16, 22, 36, 0.55);
    border: 1px solid rgba(255, 255, 255, 0.10);
    backdrop-filter: blur(9px);
    -webkit-backdrop-filter: blur(9px);
    color: #fff;
  }
  .title {
    display: flex;
    align-items: center;
    gap: 10px;
    height: 50px;
    padding: 0 20px 0 6px;
    border-radius: 25px;
    min-width: 0;
  }
  .title .icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 38px;
    height: 38px;
    border-radius: 50%;
    background: color-mix(in srgb, var(--task-color) 70%, white 10%);
    flex: none;
  }
  .title .icon ha-icon {
    --mdc-icon-size: 22px;
    color: #fff;
  }
  .title .name {
    font-size: 16px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .counter {
    margin-left: auto;
    height: 50px;
    min-width: 50px;
    padding: 0 16px;
    box-sizing: border-box;
    border-radius: 25px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 15px;
    font-weight: 600;
  }
  .body {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 24px;
    padding: 12px 24px;
    text-align: center;
    min-height: 0;
  }
  .big-icon {
    --mdc-icon-size: clamp(72px, 14vmin, 160px);
    opacity: 0.9;
  }
  .message {
    font-size: clamp(30px, 6vmin, 76px);
    font-weight: 700;
    line-height: 1.15;
    white-space: pre-line;
    overflow-wrap: anywhere;
    text-shadow: 0 2px 18px rgba(0, 0, 0, 0.18);
  }
  .actions {
    display: flex;
    gap: 14px;
    justify-content: center;
  }
  button {
    font: inherit;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    height: 72px;
    padding: 0 36px;
    border-radius: 36px;
    font-size: 22px;
    font-weight: 700;
    cursor: pointer;
    flex: 1;
    max-width: 380px;
    transition: transform 0.12s ease, opacity 0.2s ease;
  }
  button:active { transform: scale(0.97); }
  button[disabled] { opacity: 0.5; pointer-events: none; }
  button ha-icon { --mdc-icon-size: 28px; }
  .done {
    border: none;
    background: #fff;
    color: var(--task-color-strong);
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.25);
  }
  @keyframes fade { from { opacity: 0; } }
  @keyframes rise { from { opacity: 0; transform: translateY(24px) scale(0.97); } }
  @media (max-width: 600px) {
    .popup { inset: 8px; border-radius: 32px; }
    button { height: 60px; font-size: 18px; padding: 0 18px; }
  }
`;

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[ch]);
}

/** Couleur de texte lisible sur la couleur de fond (#rrggbb). */
function foregroundFor(hex) {
  const value = parseInt(hex.slice(1), 16);
  const channel = (shift) => {
    const c = ((value >> shift) & 255) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const lum = 0.2126 * channel(16) + 0.7152 * channel(8) + 0.0722 * channel(0);
  return lum > 0.45 ? "#101624" : "#ffffff";
}

/** Couleur des libellés sur le bouton blanc : la couleur, assombrie si trop claire. */
function strongColor(hex) {
  return foregroundFor(hex) === "#101624" ? "#101624" : hex;
}

function fullyDeviceId() {
  try {
    return window.fully && typeof window.fully.getDeviceId === "function"
      ? window.fully.getDeviceId()
      : null;
  } catch (_err) {
    return null;
  }
}

function forcedDisplay() {
  try {
    return window.localStorage.getItem(FORCE_KEY);
  } catch (_err) {
    return null;
  }
}

class TaskPopupOverlay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._pending = false;
  }

  set data({ task, index, total, hass }) {
    this._task = task;
    this._hass = hass;
    const lang = (hass.language || "fr").startsWith("fr") ? "fr" : "en";
    const t = I18N[lang];
    const fg = foregroundFor(task.color);
    this.style.setProperty("--task-color", task.color);
    this.style.setProperty("--task-color-strong", strongColor(task.color));
    this.style.setProperty("--task-fg", fg);
    const snooze = Math.round(task.snooze_minutes);
    const sameTask = this._renderedId === task.id;
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <div class="backdrop"></div>
      <div class="popup" role="alertdialog" aria-modal="true" aria-label="${escapeHtml(task.name)}"
           style="${sameTask ? "animation: none" : ""}">
        <div class="header">
          <div class="title glass">
            <span class="icon"><ha-icon icon="${escapeHtml(task.icon)}"></ha-icon></span>
            <span class="name">${escapeHtml(task.name)}</span>
          </div>
          ${total > 1 ? `<div class="counter glass">${index + 1} / ${total}</div>` : ""}
        </div>
        <div class="body">
          <ha-icon class="big-icon" icon="${escapeHtml(task.icon)}"></ha-icon>
          <div class="message">${escapeHtml(task.message || task.name)}</div>
        </div>
        <div class="actions">
          <button class="snooze glass" data-action="snooze">
            <ha-icon icon="mdi:alarm-snooze"></ha-icon>${t.snooze} · ${snooze} ${t.min}
          </button>
          <button class="done" data-action="ack">
            <ha-icon icon="mdi:check-bold"></ha-icon>${t.done}
          </button>
        </div>
      </div>`;
    if (sameTask) {
      this.shadowRoot.querySelector(".backdrop").style.animation = "none";
    }
    this._renderedId = task.id;
    this.shadowRoot.querySelectorAll("button").forEach((btn) =>
      btn.addEventListener("click", () => this._act(btn.dataset.action)),
    );
  }

  async _act(service) {
    if (this._pending) return;
    this._pending = true;
    this.shadowRoot.querySelectorAll("button").forEach((btn) => (btn.disabled = true));
    try {
      await this._hass.callService(DOMAIN, service, { task_id: this._task.id });
    } catch (err) {
      console.error("ha_task_popup:", err);
      this.shadowRoot.querySelectorAll("button").forEach((btn) => (btn.disabled = false));
    } finally {
      this._pending = false;
    }
  }
}

if (!customElements.get(TAG)) {
  customElements.define(TAG, TaskPopupOverlay);
}

class TaskPopupController {
  constructor() {
    this._payload = null;
    this._overlay = null;
  }

  async start() {
    const hass = await this._waitForHass();
    this._hass = hass;
    await hass.connection.subscribeMessage((payload) => this._update(payload), {
      type: `${DOMAIN}/subscribe`,
    });
    // L'objet hass change à chaque mise à jour d'état : on garde la dernière version.
    setInterval(() => {
      const current = this._root()?.hass;
      if (current) this._hass = current;
    }, 5000);
  }

  _root() {
    return document.querySelector("home-assistant");
  }

  _waitForHass() {
    return new Promise((resolve) => {
      const check = () => {
        const hass = this._root()?.hass;
        if (hass && hass.connection) resolve(hass);
        else setTimeout(check, 500);
      };
      check();
    });
  }

  _allowed(payload) {
    const forced = forcedDisplay();
    if (forced === "1") return true;
    if (forced === "0") return false;
    if (payload.display_on === "all") return true;
    const id = fullyDeviceId();
    return Boolean(id) && (payload.fully_ids || []).includes(id);
  }

  _update(payload) {
    this._payload = payload;
    const tasks = payload.tasks || [];
    if (!tasks.length || !this._allowed(payload)) {
      this._close();
      return;
    }
    if (!this._overlay || !this._overlay.isConnected) {
      this._overlay = document.createElement(TAG);
      document.body.appendChild(this._overlay);
    }
    this._overlay.data = { task: tasks[0], index: 0, total: tasks.length, hass: this._hass };
  }

  _close() {
    if (this._overlay) {
      this._overlay.remove();
      this._overlay = null;
    }
  }
}

if (!window.__haTaskPopup) {
  window.__haTaskPopup = new TaskPopupController();
  window.__haTaskPopup.start().catch((err) => console.error("ha_task_popup:", err));
}
