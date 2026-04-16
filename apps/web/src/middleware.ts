import { auth } from "@/lib/auth";
import { NextResponse } from "next/server";
import { buildPluginCsp } from "@/lib/csp";

// Routes accessible only from the plugin WebView
const pluginPaths = ["/plugin"];

// Routes that require auth but are accessed from the system browser (not WebView)
const deviceAuthPaths = ["/link"];

// Routes that never require auth
const publicPaths = ["/", "/login", "/api/auth", "/api/ai", "/api/plugin", "/api/stripe/webhook"];

/**
 * Fresh base64 nonce per request. The CSP demands a value that cannot be
 * guessed by an injected script; `crypto.randomUUID()` is 128 bits of
 * entropy which is well beyond what browsers require.
 */
function generateNonce(): string {
  return Buffer.from(crypto.randomUUID()).toString("base64");
}

export default auth((req) => {
  const { pathname, searchParams } = req.nextUrl;
  const isAuthenticated = !!req.auth;
  const isPluginContext = searchParams.get("context") === "plugin";
  const isPluginPath = pluginPaths.some((p) => pathname.startsWith(p));

  // Any response that renders the plugin UI needs a CSP nonce.
  // That's either a direct /plugin/* path OR the / rewrite target from ?context=plugin.
  const needsCsp = isPluginPath || (isPluginContext && pathname === "/");
  const nonce = needsCsp ? generateNonce() : null;

  // Forward x-nonce on the request so Next.js hydration scripts + server
  // components can read it via headers().get('x-nonce') and embed the
  // matching `nonce` attribute. See apps/web/src/lib/csp.ts.
  const requestHeaders = new Headers(req.headers);
  if (nonce) requestHeaders.set("x-nonce", nonce);

  function withCsp(response: NextResponse): NextResponse {
    if (nonce) {
      response.headers.set("Content-Security-Policy", buildPluginCsp({ nonce }));
    }
    return response;
  }

  // Plugin context rewrite: /?context=plugin → /plugin
  if (isPluginContext && pathname === "/") {
    const pluginUrl = new URL("/plugin", req.nextUrl.origin);
    pluginUrl.search = searchParams.toString();
    return withCsp(
      NextResponse.rewrite(pluginUrl, { request: { headers: requestHeaders } })
    );
  }

  const isPublic =
    pathname === "/" ||
    publicPaths.some((p) => p !== "/" && pathname.startsWith(p));

  // --- Plugin routes: only accessible with ?context=plugin ---
  if (isPluginPath && !isPluginContext) {
    return NextResponse.redirect(new URL("/", req.nextUrl.origin));
  }

  // --- Plugin context: block access to browser routes ---
  if (isPluginContext && !isPluginPath && !isPublic) {
    return NextResponse.redirect(
      new URL("/plugin?context=plugin", req.nextUrl.origin)
    );
  }

  // Public routes and plugin routes don't require session
  if (isPublic || isPluginPath) {
    return withCsp(
      NextResponse.next({ request: { headers: requestHeaders } })
    );
  }

  // Protected browser routes: require NextAuth session
  if (!isAuthenticated) {
    const loginUrl = new URL("/login", req.nextUrl.origin);
    loginUrl.searchParams.set("callbackUrl", req.nextUrl.href);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
});

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt).*)",
  ],
};
