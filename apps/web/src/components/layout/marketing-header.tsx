import Link from "next/link";
import { buttonVariants } from "@/components/ui/button-variants";
import { cn } from "@/lib/utils";

export function MarketingHeader() {
  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-16 items-center justify-between">
        <Link href="/" className="flex items-center space-x-2">
          <span className="text-xl font-bold">Studio AI</span>
        </Link>
        <nav className="flex items-center space-x-6">
          <Link
            href="/#features"
            className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            Features
          </Link>
          <Link
            href="/#pricing"
            className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            Pricing
          </Link>
          <Link
            href="/login"
            className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
          >
            Sign In
          </Link>
          <Link
            href="/login"
            className={cn(buttonVariants({ size: "sm" }))}
          >
            Get Started
          </Link>
        </nav>
      </div>
    </header>
  );
}
