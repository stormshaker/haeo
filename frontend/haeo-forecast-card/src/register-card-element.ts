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

/** How long to keep re-registering after the bundle loads. */
const RETRY_INTERVAL_MS = 50;
const RETRY_TICKS = 200;

/**
 * @returns A function that stops the retries early. Production never calls it — the
 * retries stop on their own — but a test that loads a card module must, so the interval
 * cannot outlive the test environment it captured.
 */
export function registerCardElement(tag: string, ctor: CustomElementConstructor): () => void {
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
    if (ticks >= RETRY_TICKS) {
      clearInterval(timer);
    }
  }, RETRY_INTERVAL_MS);

  return () => {
    clearInterval(timer);
  };
}
