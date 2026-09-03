import { buildHubConfigForm } from "./config-form";
import { discoverHaeoHubEntryId } from "./hub-selection";
import type { HassLike } from "./series";
import type { ForecastCardConfig } from "./types";
import type { ForecastCardController } from "./forecast-card-controller";

const FALLBACK_CARD_WIDTH_PX = 640;
const FALLBACK_CARD_SIZE_ROWS = 6;
const FALLBACK_GRID_ROWS = 5;

/**
 * Thin custom element for `haeo-forecast-card`.
 *
 * This class is intentionally tiny and free of heavy imports (no preact, MobX,
 * or SVG view code) so that `customElements.define` runs immediately when the
 * bundle loads. Home Assistant only guarantees a custom card via
 * `customElements.whenDefined` plus a short timeout, so gating registration
 * behind a large dependency graph causes the intermittent "Custom element
 * doesn't exist" race. The heavy rendering stack is loaded lazily on first use.
 */
export class HaeoForecastCard extends HTMLElement {
  private static nextInstanceId = 0;
  private readonly instanceId = HaeoForecastCard.nextInstanceId++;
  private controller: ForecastCardController | null = null;
  private controllerPromise: Promise<ForecastCardController> | null = null;
  private _config: ForecastCardConfig | null = null;
  private _hass: HassLike | null = null;
  private isConnected_ = false;

  setConfig(config: ForecastCardConfig): void {
    this._config = config;
    if (this.controller) {
      this.controller.setConfig(config);
    } else {
      void this.ensureController();
    }
  }

  static getConfigForm(): ReturnType<typeof buildHubConfigForm> {
    return buildHubConfigForm();
  }

  static getStubConfig(hass?: HassLike): Omit<ForecastCardConfig, "type"> {
    const stub: Omit<ForecastCardConfig, "type"> = { title: "HAEO forecast" };
    if (hass === undefined) {
      return stub;
    }
    const hubEntryId = discoverHaeoHubEntryId(hass);
    if (hubEntryId !== null) {
      stub.hub_entry_id = hubEntryId;
    }
    return stub;
  }

  set hass(hass: HassLike | null) {
    this._hass = hass;
    if (this.controller) {
      this.controller.setHass(hass);
    } else {
      void this.ensureController();
    }
  }

  get hass(): HassLike | null {
    return this._hass;
  }

  connectedCallback(): void {
    this.isConnected_ = true;
    if (this.controller) {
      this.controller.connected();
      return;
    }
    void this.ensureController();
  }

  disconnectedCallback(): void {
    this.isConnected_ = false;
    this.controller?.disconnected();
  }

  getCardSize(): number {
    return this.controller?.getCardSize() ?? FALLBACK_CARD_SIZE_ROWS;
  }

  getGridOptions(): {
    rows: number;
    min_rows: number;
    columns: "full";
  } {
    return (
      this.controller?.getGridOptions() ?? {
        rows: FALLBACK_GRID_ROWS,
        min_rows: FALLBACK_GRID_ROWS - 1,
        columns: "full",
      }
    );
  }

  getCardWidth(): number {
    if (this.controller) {
      return this.controller.getCardWidth();
    }
    const width = this.getBoundingClientRect().width;
    return width > 0 ? width : FALLBACK_CARD_WIDTH_PX;
  }

  /**
   * Load the heavy rendering controller on demand and replay any buffered
   * config/hass/connection state into it. Registration of the element never
   * depends on this completing.
   */
  private async ensureController(): Promise<ForecastCardController> {
    this.controllerPromise ??= import("./forecast-card-controller").then(({ ForecastCardController }) => {
      const controller = new ForecastCardController(this, this.instanceId);
      this.controller = controller;
      if (this._config) {
        controller.setConfig(this._config);
      }
      if (this._hass) {
        controller.setHass(this._hass);
      }
      if (this.isConnected_) {
        controller.connected();
      }
      return controller;
    });
    return this.controllerPromise;
  }
}

/**
 * Register a card element, and keep it registered.
 *
 * Home Assistant can replace `window.customElements` with the scoped custom element
 * registry polyfill *after* this module has already run. The replacement registry does
 * not carry over registrations made against the native one, so an element registered
 * moments earlier silently disappears and Lovelace renders "Custom element doesn't
 * exist" for a bundle that loaded, ran, and registered without error.
 *
 * Measured on a failing load: at module evaluation `customElements.define` was still
 * native, the define did not throw, and `customElements.get(tag)` returned the
 * constructor immediately afterwards — yet the element was gone by the time Lovelace
 * built the card. On a load that succeeded, the polyfill was already installed when the
 * module ran, so the registration went into the registry that survived.
 *
 * Registering once is therefore not enough, and neither is retrying only until the first
 * success. This re-registers whenever the element goes missing, for long enough to cover
 * the swap, then stops.
 */
function registerCardElement(tag: string, ctor: CustomElementConstructor): void {
  const ensure = (): void => {
    if (customElements.get(tag) !== undefined) {
      return;
    }
    try {
      customElements.define(tag, ctor);
    } catch {
      // Another evaluation of this bundle won the race; nothing to do.
    }
  };

  ensure();

  let ticks = 0;
  const timer = setInterval(() => {
    ticks += 1;
    ensure();
    if (ticks >= 200) {
      clearInterval(timer);
    }
  }, 50);
}

registerCardElement("haeo-forecast-card", HaeoForecastCard);
