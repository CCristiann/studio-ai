import { auth } from "@/lib/auth";
import { NextResponse } from "next/server";

export default auth((req) => {
  const { pathname, searchParams } = req.nextUrl;
  const isAuthenticated = !!req.auth;

  // Public routes that don't require auth
  const publicPaths = ["/login", "/api/auth", "/api/stripe/webhook"];
  const isPublic =
    pathname === "/" ||
    publicPaths.some((path) => pathname.startsWith(path));

  if (isPublic) return NextResponse.next();

  // All protected routes (dashboard + plugin): require NextAuth session
  if (!isAuthenticated) {
    const loginUrl = new URL("/login", req.nextUrl.origin);
    // Preserve context param so after login we redirect back correctly
    const callbackUrl = req.nextUrl.href;
    loginUrl.searchParams.set("callbackUrl", callbackUrl);
    return NextResponse.redirect(loginUrl);
  }

  // Plugin context rewrite: / with ?context=plugin → /plugin
  const isPluginContext = searchParams.get("context") === "plugin";
  if (isPluginContext && pathname === "/") {
    const pluginUrl = new URL("/plugin", req.nextUrl.origin);
    pluginUrl.search = searchParams.toString();
    return NextResponse.rewrite(pluginUrl);
  }

  return NextResponse.next();
});

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt).*)",
  ],
};
