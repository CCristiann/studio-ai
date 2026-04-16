import { describe, it, expect } from "vitest";
import { buildPluginCsp } from "./csp";

describe("buildPluginCsp", () => {
  const nonce = "abc123==";

  it("single-line output (whitespace collapsed)", () => {
    const csp = buildPluginCsp({ nonce });
    expect(csp).not.toContain("\n");
    // Separator is semicolon + space — no double spaces.
    expect(csp).not.toMatch(/ {2,}/);
  });

  it("includes the nonce on script-src and style-src", () => {
    const csp = buildPluginCsp({ nonce });
    expect(csp).toContain(`script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`);
    expect(csp).toContain(`style-src 'self' 'nonce-${nonce}'`);
  });

  it("locks connect-src to self — the exfiltration prevention", () => {
    const csp = buildPluginCsp({ nonce });
    expect(csp).toContain("connect-src 'self'");
    // Must NOT contain any external connect-src origin.
    expect(csp).not.toMatch(/connect-src[^;]*https?:\/\//);
  });

  it("blocks framing entirely with frame-ancestors 'none'", () => {
    const csp = buildPluginCsp({ nonce });
    expect(csp).toContain("frame-ancestors 'none'");
  });

  it("allows blob: and data: for images (Canvas + inline icons)", () => {
    const csp = buildPluginCsp({ nonce });
    expect(csp).toMatch(/img-src 'self' blob: data:/);
  });

  it("does not include 'unsafe-inline' or 'unsafe-eval' on scripts", () => {
    const csp = buildPluginCsp({ nonce });
    const scriptSrc = csp.split(";").find((d) => d.trim().startsWith("script-src"))!;
    expect(scriptSrc).not.toContain("'unsafe-inline'");
    expect(scriptSrc).not.toContain("'unsafe-eval'");
  });

  it("includes default-src 'self' as the fallback", () => {
    const csp = buildPluginCsp({ nonce });
    expect(csp).toMatch(/(^|; )default-src 'self'/);
  });

  it("includes object-src 'none' (no legacy plugins)", () => {
    const csp = buildPluginCsp({ nonce });
    expect(csp).toContain("object-src 'none'");
  });

  it("includes base-uri 'self' (prevents <base> abuse)", () => {
    const csp = buildPluginCsp({ nonce });
    expect(csp).toContain("base-uri 'self'");
  });

  it("includes form-action 'self'", () => {
    const csp = buildPluginCsp({ nonce });
    expect(csp).toContain("form-action 'self'");
  });

  it("different nonces produce different CSP strings", () => {
    const a = buildPluginCsp({ nonce: "nonce-a" });
    const b = buildPluginCsp({ nonce: "nonce-b" });
    expect(a).not.toEqual(b);
  });
});
