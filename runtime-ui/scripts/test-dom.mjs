import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://localhost/',
  pretendToBeVisual: true,
});
for (const name of ['window', 'document', 'navigator', 'HTMLElement', 'HTMLIFrameElement',
  'HTMLFormElement', 'DocumentFragment', 'Element', 'Node', 'Event', 'CustomEvent', 'MouseEvent',
  'MessageEvent', 'MutationObserver', 'DOMParser']) {
  Object.defineProperty(globalThis, name, { configurable: true, writable: true,
    value: name === 'window' ? dom.window : dom.window[name] });
}
globalThis.getComputedStyle = dom.window.getComputedStyle.bind(dom.window);
dom.window.HTMLElement.prototype.scrollIntoView = () => {};
globalThis.requestAnimationFrame = dom.window.requestAnimationFrame.bind(dom.window);
globalThis.cancelAnimationFrame = dom.window.cancelAnimationFrame.bind(dom.window);
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
