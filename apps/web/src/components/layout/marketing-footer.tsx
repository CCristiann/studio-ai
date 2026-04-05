import Link from "next/link";
import { Separator } from "@/components/ui/separator";

export function MarketingFooter() {
  return (
    <footer className="border-t">
      <div className="mx-auto max-w-6xl px-6 py-12">
        <div className="flex flex-col items-center justify-between gap-6 md:flex-row">
          <div>
            <span className="text-lg font-bold tracking-tight">Studio AI</span>
            <p className="mt-1 text-sm text-muted-foreground">
              AI-powered DAW control for musicians
            </p>
          </div>
          <nav className="flex gap-6">
            <Link
              href="/#features"
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              Features
            </Link>
            <Link
              href="/#pricing"
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              Pricing
            </Link>
            <Link
              href="/login"
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              Sign In
            </Link>
          </nav>
        </div>
        <Separator className="my-8" />
        <p className="text-center text-sm text-muted-foreground">
          &copy; {new Date().getFullYear()} Studio AI. All rights reserved.
        </p>
      </div>
    </footer>
  );
}
