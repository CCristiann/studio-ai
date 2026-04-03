import { auth } from "@/lib/auth";
import { NextResponse } from "next/server";

// Routes accessible only from the plugin WebView
const pluginPaths = ["/plugin", "/auth/device"];

// Routes that never require auth
const publicPaths = ["/", "/login", "/api/auth", "/api/stripe/webhook"];

export default auth((req) => {
  const { pathname, searchParams } = req.nextUrl;
  const isAuthenticated = !!req.auth;
  const isPluginContext = searchParams.get("context") === "plugin";

  // Plugin context rewrite: /?context=plugin → /plugin
  if (isPluginContext && pathname === "/") {
    const pluginUrl = new URL("/plugin", req.nextUrl.origin);
    pluginUrl.search = searchParams.toString();
    return NextResponse.rewrite(pluginUrl);
  }

  const isPluginRoute = pluginPaths.some((p) => pathname.startsWith(p));
  const isPublic =
    pathname === "/" ||
    publicPaths.some((p) => p !== "/" && pathname.startsWith(p));

  // --- Plugin routes: only accessible with ?context=plugin ---
  if (isPluginRoute && !isPluginContext) {
    return NextResponse.redirect(new URL("/", req.nextUrl.origin));
  }

  // --- Plugin context: block access to browser routes ---
  if (isPluginContext && !isPluginRoute && !isPublic) {
    return NextResponse.redirect(
      new URL("/plugin?context=plugin", req.nextUrl.origin)
    );
  }

  // Public routes and plugin routes don't require session
  if (isPublic || isPluginRoute) return NextResponse.next();

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
