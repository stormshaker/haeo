import { buildHubConfigForm } from "./config-form";
import { discoverHaeoHubEntryId } from "./hub-selection";
import type { HassLike } from "./series";
import type { TopologyCardController } from "./topology-card-controller";
import { topologyCardSize, TOPOLOGY_DEFAULT_LAYOUT_HEIGHT_PX } from "./topology-layout";
import type { TopologyCardConfig } from "./types";

const FALLBACK_CARD_SIZE_ROWS = topologyCardSize(TOPOLOGY_DEFAULT_LAYOUT_HEIGHT_PX);

function buildTopologyStubConfig(hass: HassLike): Omit<TopologyCardConfig, "type"> {
  const stub: Omit<TopologyCardConfig, "type"> = { title: "HAEO network topology" };
  const hubEntryId = discoverHaeoHubEntryId(hass);
  if (hubEntryId !== null) {
    stub.hub_entry_id = hubEntryId;
  }
  return stub;
}

/**
 * Thin custom element for `haeo-topology-card`.
 *
 * Kept free of heavy imports (preact, ELK, the SVG view) so that
 * `customElements.define` runs immediately when the bundle loads, avoiding the
 * Home Assistant "Custom element doesn't exist" registration race. The heavy
 * rendering controller is imported lazily on first use.
 */
export class HaeoTopologyCard extends HTMLElement {
  private controller: TopologyCardController | null = null;
  private controllerPromise: Promise<TopologyCardController> | null = null;
  private _config: TopologyCardConfig = { type: "custom:haeo-topology-card" };
  private _hass: HassLike | null = null;
  private isConnected_ = false;

  setConfig(config: TopologyCardConfig): void {
    this._config = { ...config, type: "custom:haeo-topology-card" };
    if (this.controller) {
      this.controller.setConfig(this._config);
    } else {
      void this.ensureController();
    }
  }

  static getConfigForm(): ReturnType<typeof buildHubConfigForm> {
    return buildHubConfigForm();
  }

  static getStubConfig(hass?: HassLike): Omit<TopologyCardConfig, "type"> {
    if (hass === undefined) {
      return { title: "HAEO network topology" };
    }
    return buildTopologyStubConfig(hass);
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
    if (this.controller) {
      return this.controller.getGridOptions();
    }
    return {
      rows: FALLBACK_CARD_SIZE_ROWS,
      min_rows: Math.max(3, FALLBACK_CARD_SIZE_ROWS - 1),
      columns: "full",
    };
  }

  private async ensureController(): Promise<TopologyCardController> {
    this.controllerPromise ??= import("./topology-card-controller").then(({ TopologyCardController }) => {
      const controller = new TopologyCardController(this);
      this.controller = controller;
      controller.setConfig(this._config);
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

registerCardElement("haeo-topology-card", HaeoTopologyCard);
