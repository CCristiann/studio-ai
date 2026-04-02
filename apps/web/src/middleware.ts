import { auth } from "@/lib/auth";
import { NextResponse } from "next/server";

export default auth((req) => {
  const { pathname, searchParams } = req.nextUrl;
  const isPluginContext = searchParams.get("context") === "plugin";
  const isAuthenticated = !!req.auth;

  // Public routes that don't require auth
  const publicPaths = ["/", "/login", "/api/auth", "/api/stripe/webhook"];
  const isPublic = publicPaths.some((path) => pathname.startsWith(path));

  // Plugin context: redirect unauthenticated to login with context param
  if (isPluginContext && !isAuthenticated && !isPublic) {
    const loginUrl = new URL("/login", req.nextUrl.origin);
    loginUrl.searchParams.set("context", "plugin");
    loginUrl.searchParams.set("callbackUrl", req.nextUrl.href);
    return NextResponse.redirect(loginUrl);
  }

  // Dashboard routes: require auth
  if (pathname.startsWith("/dashboard") && !isAuthenticated) {
    const loginUrl = new URL("/login", req.nextUrl.origin);
    loginUrl.searchParams.set("callbackUrl", req.nextUrl.href);
    return NextResponse.redirect(loginUrl);
  }

  // Plugin context: rewrite to plugin layout
  if (isPluginContext && pathname === "/") {
    const pluginUrl = new URL("/plugin", req.nextUrl.origin);
    pluginUrl.searchParams.set("context", "plugin");
    return NextResponse.rewrite(pluginUrl);
  }

  return NextResponse.next();
});

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt).*)",
  ],
};
