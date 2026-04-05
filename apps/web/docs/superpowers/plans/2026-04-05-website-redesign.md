# Website Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Studio AI web app (landing page, dashboard, login) using shadcn/ui components with a monochrome Apple/Sana-inspired theme, supporting light and dark mode.

**Architecture:** Replace existing custom UI components with shadcn primitives. Add next-themes for dark mode with system preference + manual toggle. Extract landing page into section components. Add settings page to dashboard. Keep all API routes, plugin routes, and backend logic untouched.

**Tech Stack:** Next.js 15, React 19, Tailwind CSS v4, shadcn/ui (base-nova style), next-themes, Lucide icons

---

## File Map

### Files to Create
- `src/components/layout/theme-toggle.tsx` — Sun/moon dropdown toggle (shared between marketing + dashboard)
- `src/components/layout/marketing-footer.tsx` — Footer with links and copyright
- `src/components/layout/dashboard-topbar.tsx` — Page title, theme toggle, user dropdown
- `src/components/sections/hero.tsx` — Landing hero section
- `src/components/sections/features.tsx` — Landing features grid
- `src/components/sections/pricing.tsx` — Landing pricing cards with annual toggle
- `src/app/(dashboard)/dashboard/settings/page.tsx` — User settings page
- `src/components/theme-provider.tsx` — next-themes ThemeProvider wrapper (client component)

### Files to Modify
- `package.json` — Add next-themes dependency
- `src/app/globals.css` — Update theme variables to pure monochrome
- `src/app/layout.tsx` — Add ThemeProvider, suppressHydrationWarning
- `src/app/(marketing)/layout.tsx` — Add footer component
- `src/app/(marketing)/page.tsx` — Replace inline sections with section components
- `src/app/login/page.tsx` — Redesign with shadcn components
- `src/app/(dashboard)/layout.tsx` — Add topbar, responsive sidebar with Sheet
- `src/app/(dashboard)/dashboard/page.tsx` — Redesign overview page
- `src/app/(dashboard)/dashboard/billing/page.tsx` — Redesign with pricing cards
- `src/components/layout/marketing-header.tsx` — Redesign with shadcn navigation
- `src/components/layout/dashboard-sidebar.tsx` — Redesign with icons, avatar, Sheet support

### Files to Delete
- `src/components/ui/button-variants.ts` — Replaced by shadcn button
- `src/components/ui/button.tsx` — Replaced by shadcn button
- `src/components/ui/input.tsx` — Replaced by shadcn input
- `src/components/ui/card.tsx` — Replaced by shadcn card

### Files Untouched
- `src/app/(plugin)/**` — All plugin routes
- `src/app/link/**` — Device link page
- `src/app/api/**` — All API routes
- `src/lib/**` — All lib files (auth, stripe, etc.)
- `src/middleware.ts` — Route protection
- `src/components/chat/**` — Chat interface (plugin)
- `src/hooks/use-plugin-context.ts` — Plugin hook

---

## Task 1: Install dependencies and shadcn components

**Files:**
- Modify: `package.json`
- Modify: `src/components/ui/*` (shadcn CLI overwrites)
- Modify: `components.json` (shadcn CLI updates)

- [ ] **Step 1: Install next-themes**

```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
pnpm add next-themes
```

- [ ] **Step 2: Remove old custom UI components**

```bash
rm src/components/ui/button.tsx src/components/ui/button-variants.ts src/components/ui/input.tsx src/components/ui/card.tsx
```

- [ ] **Step 3: Install shadcn components**

```bash
pnpm dlx shadcn@latest add button card input label badge separator avatar dropdown-menu switch dialog sheet navigation-menu
```

Expected: Each component installed to `src/components/ui/` with shadcn defaults.

- [ ] **Step 4: Verify installation**

```bash
ls src/components/ui/
```

Expected: `button.tsx`, `card.tsx`, `input.tsx`, `label.tsx`, `badge.tsx`, `separator.tsx`, `avatar.tsx`, `dropdown-menu.tsx`, `switch.tsx`, `dialog.tsx`, `sheet.tsx`, `navigation-menu.tsx` (plus any sub-dependencies like `popover.tsx`).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: install next-themes and shadcn components

Replace custom @base-ui button/input/card with shadcn primitives.
Install additional shadcn components for redesign."
```

---

## Task 2: Update theme to monochrome Apple/Sana-inspired

**Files:**
- Modify: `src/app/globals.css`

- [ ] **Step 1: Replace globals.css with monochrome theme**

Replace the full content of `src/app/globals.css` with:

```css
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";

@custom-variant dark (&:is(.dark *));

@theme inline {
    --font-heading: var(--font-sans);
    --font-sans: var(--font-sans);
    --color-sidebar-ring: var(--sidebar-ring);
    --color-sidebar-border: var(--sidebar-border);
    --color-sidebar-accent-foreground: var(--sidebar-accent-foreground);
    --color-sidebar-accent: var(--sidebar-accent);
    --color-sidebar-primary-foreground: var(--sidebar-primary-foreground);
    --color-sidebar-primary: var(--sidebar-primary);
    --color-sidebar-foreground: var(--sidebar-foreground);
    --color-sidebar: var(--sidebar);
    --color-chart-5: var(--chart-5);
    --color-chart-4: var(--chart-4);
    --color-chart-3: var(--chart-3);
    --color-chart-2: var(--chart-2);
    --color-chart-1: var(--chart-1);
    --color-ring: var(--ring);
    --color-input: var(--input);
    --color-border: var(--border);
    --color-destructive: var(--destructive);
    --color-accent-foreground: var(--accent-foreground);
    --color-accent: var(--accent);
    --color-muted-foreground: var(--muted-foreground);
    --color-muted: var(--muted);
    --color-secondary-foreground: var(--secondary-foreground);
    --color-secondary: var(--secondary);
    --color-primary-foreground: var(--primary-foreground);
    --color-primary: var(--primary);
    --color-popover-foreground: var(--popover-foreground);
    --color-popover: var(--popover);
    --color-card-foreground: var(--card-foreground);
    --color-card: var(--card);
    --color-foreground: var(--foreground);
    --color-background: var(--background);
    --radius-sm: calc(var(--radius) * 0.6);
    --radius-md: calc(var(--radius) * 0.8);
    --radius-lg: var(--radius);
    --radius-xl: calc(var(--radius) * 1.4);
    --radius-2xl: calc(var(--radius) * 1.8);
    --radius-3xl: calc(var(--radius) * 2.2);
    --radius-4xl: calc(var(--radius) * 2.6);
}

:root {
    --background: oklch(1 0 0);
    --foreground: oklch(0.145 0 0);
    --card: oklch(1 0 0);
    --card-foreground: oklch(0.145 0 0);
    --popover: oklch(1 0 0);
    --popover-foreground: oklch(0.145 0 0);
    --primary: oklch(0.145 0 0);
    --primary-foreground: oklch(0.985 0 0);
    --secondary: oklch(0.965 0 0);
    --secondary-foreground: oklch(0.205 0 0);
    --muted: oklch(0.965 0 0);
    --muted-foreground: oklch(0.556 0 0);
    --accent: oklch(0.965 0 0);
    --accent-foreground: oklch(0.205 0 0);
    --destructive: oklch(0.577 0.245 27.325);
    --border: oklch(0.922 0 0);
    --input: oklch(0.922 0 0);
    --ring: oklch(0.708 0 0);
    --chart-1: oklch(0.87 0 0);
    --chart-2: oklch(0.7 0 0);
    --chart-3: oklch(0.556 0 0);
    --chart-4: oklch(0.439 0 0);
    --chart-5: oklch(0.269 0 0);
    --radius: 0.625rem;
    --sidebar: oklch(0.985 0 0);
    --sidebar-foreground: oklch(0.145 0 0);
    --sidebar-primary: oklch(0.145 0 0);
    --sidebar-primary-foreground: oklch(0.985 0 0);
    --sidebar-accent: oklch(0.965 0 0);
    --sidebar-accent-foreground: oklch(0.205 0 0);
    --sidebar-border: oklch(0.922 0 0);
    --sidebar-ring: oklch(0.708 0 0);
}

.dark {
    --background: oklch(0.12 0 0);
    --foreground: oklch(0.985 0 0);
    --card: oklch(0.17 0 0);
    --card-foreground: oklch(0.985 0 0);
    --popover: oklch(0.17 0 0);
    --popover-foreground: oklch(0.985 0 0);
    --primary: oklch(0.985 0 0);
    --primary-foreground: oklch(0.12 0 0);
    --secondary: oklch(0.22 0 0);
    --secondary-foreground: oklch(0.985 0 0);
    --muted: oklch(0.22 0 0);
    --muted-foreground: oklch(0.708 0 0);
    --accent: oklch(0.22 0 0);
    --accent-foreground: oklch(0.985 0 0);
    --destructive: oklch(0.704 0.191 22.216);
    --border: oklch(0.26 0 0);
    --input: oklch(0.26 0 0);
    --ring: oklch(0.556 0 0);
    --chart-1: oklch(0.87 0 0);
    --chart-2: oklch(0.7 0 0);
    --chart-3: oklch(0.556 0 0);
    --chart-4: oklch(0.439 0 0);
    --chart-5: oklch(0.269 0 0);
    --sidebar: oklch(0.15 0 0);
    --sidebar-foreground: oklch(0.985 0 0);
    --sidebar-primary: oklch(0.985 0 0);
    --sidebar-primary-foreground: oklch(0.12 0 0);
    --sidebar-accent: oklch(0.22 0 0);
    --sidebar-accent-foreground: oklch(0.985 0 0);
    --sidebar-border: oklch(0.26 0 0);
    --sidebar-ring: oklch(0.556 0 0);
}

@layer base {
  * {
    @apply border-border outline-ring/50;
  }
  body {
    @apply bg-background text-foreground;
  }
  html {
    @apply font-sans;
  }
}
```

Key changes from existing theme:
- `:root` primary changed from `oklch(0.205 0 0)` to `oklch(0.145 0 0)` — deeper black for buttons
- `.dark` background changed from `oklch(0.145 0 0)` to `oklch(0.12 0 0)` — slightly darker
- `.dark` primary inverted to white (`oklch(0.985 0 0)`) with dark foreground — Apple-style inversion
- `.dark` card changed from `oklch(0.205 0 0)` to `oklch(0.17 0 0)` — subtler elevation
- `.dark` border/input changed to `oklch(0.26 0 0)` — slightly visible borders
- `.dark` sidebar-primary changed from blue (`oklch(0.488 0.243 264.376)`) to white — monochrome consistency
- Chart colors made consistent between light/dark

- [ ] **Step 2: Verify the app compiles**

```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
pnpm dev &
sleep 5 && kill %1
```

Expected: No CSS compilation errors.

- [ ] **Step 3: Commit**

```bash
git add src/app/globals.css
git commit -m "style: update theme to monochrome Apple/Sana-inspired palette

Deepen primary black, invert dark mode buttons to white-on-black,
remove blue sidebar accent, unify chart colors across modes."
```

---

## Task 3: Add ThemeProvider and update root layout

**Files:**
- Create: `src/components/theme-provider.tsx`
- Modify: `src/app/layout.tsx`

- [ ] **Step 1: Create ThemeProvider wrapper**

Create `src/components/theme-provider.tsx`:

```tsx
"use client"

import { ThemeProvider as NextThemesProvider } from "next-themes"

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  )
}
```

- [ ] **Step 2: Update root layout**

Replace `src/app/layout.tsx` with:

```tsx
import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";

const geist = Geist({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: "Studio AI",
  description: "AI-powered DAW control for musicians",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={geist.variable} suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased">
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
```

Changes from existing:
- Removed Inter font (only Geist needed)
- Removed `cn()` call on html className (unnecessary, just use template literal)
- Added `suppressHydrationWarning` to `<html>`
- Wrapped children with `<ThemeProvider>`
- Moved `font-sans` to body className

- [ ] **Step 3: Commit**

```bash
git add src/components/theme-provider.tsx src/app/layout.tsx
git commit -m "feat: add ThemeProvider with system preference and class strategy"
```

---

## Task 4: Create theme toggle component

**Files:**
- Create: `src/components/layout/theme-toggle.tsx`

- [ ] **Step 1: Create the toggle component**

Create `src/components/layout/theme-toggle.tsx`:

```tsx
"use client"

import { useTheme } from "next-themes"
import { Moon, Sun, Monitor } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

export function ThemeToggle() {
  const { setTheme } = useTheme()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon">
          <Sun className="size-4 scale-100 rotate-0 transition-transform dark:scale-0 dark:-rotate-90" />
          <Moon className="absolute size-4 scale-0 rotate-90 transition-transform dark:scale-100 dark:rotate-0" />
          <span className="sr-only">Toggle theme</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => setTheme("light")}>
          <Sun className="mr-2 size-4" />
          Light
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("dark")}>
          <Moon className="mr-2 size-4" />
          Dark
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("system")}>
          <Monitor className="mr-2 size-4" />
          System
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add src/components/layout/theme-toggle.tsx
git commit -m "feat: add theme toggle dropdown with light/dark/system options"
```

---

## Task 5: Redesign marketing header

**Files:**
- Modify: `src/components/layout/marketing-header.tsx`

- [ ] **Step 1: Replace marketing header**

Replace `src/components/layout/marketing-header.tsx` with:

```tsx
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/layout/theme-toggle";

export function MarketingHeader() {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-border/50 bg-background/80 backdrop-blur-lg">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <Link href="/" className="text-xl font-bold tracking-tight">
          Studio AI
        </Link>
        <nav className="hidden items-center gap-8 md:flex">
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
        </nav>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Button variant="ghost" size="sm" asChild>
            <Link href="/login">Sign In</Link>
          </Button>
          <Button size="sm" asChild>
            <Link href="/login">Get Started</Link>
          </Button>
        </div>
      </div>
    </header>
  );
}
```

Changes from existing:
- Removed `buttonVariants` import (using shadcn `Button` with `asChild`)
- Added `ThemeToggle` component
- Changed container to `max-w-6xl mx-auto px-6` (Apple-like centered layout)
- Added `backdrop-blur-lg` and `border-border/50` for subtle glassmorphism
- Hidden nav on mobile (to be handled later if needed)
- Removed Plugin link (plugin is separate context)

- [ ] **Step 2: Commit**

```bash
git add src/components/layout/marketing-header.tsx
git commit -m "feat: redesign marketing header with shadcn buttons and theme toggle"
```

---

## Task 6: Create marketing footer

**Files:**
- Create: `src/components/layout/marketing-footer.tsx`
- Modify: `src/app/(marketing)/layout.tsx`

- [ ] **Step 1: Create footer component**

Create `src/components/layout/marketing-footer.tsx`:

```tsx
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
```

- [ ] **Step 2: Update marketing layout to use footer**

Replace `src/app/(marketing)/layout.tsx` with:

```tsx
import { MarketingHeader } from "@/components/layout/marketing-header";
import { MarketingFooter } from "@/components/layout/marketing-footer";

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <MarketingHeader />
      <main className="flex-1">{children}</main>
      <MarketingFooter />
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add src/components/layout/marketing-footer.tsx src/app/\(marketing\)/layout.tsx
git commit -m "feat: add marketing footer with links and separator"
```

---

## Task 7: Create landing page section components

**Files:**
- Create: `src/components/sections/hero.tsx`
- Create: `src/components/sections/features.tsx`
- Create: `src/components/sections/pricing.tsx`
- Modify: `src/app/(marketing)/page.tsx`

- [ ] **Step 1: Create hero section**

Create `src/components/sections/hero.tsx`:

```tsx
import Link from "next/link";
import { Button } from "@/components/ui/button";

export function Hero() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-24 md:py-32">
      <div className="flex flex-col items-center text-center">
        <h1 className="max-w-3xl text-4xl font-bold tracking-tight md:text-5xl lg:text-6xl">
          AI-Powered Music Production
        </h1>
        <p className="mt-6 max-w-xl text-lg text-muted-foreground">
          Control your Digital Audio Workstation with natural language. Set BPM,
          add tracks, manage your project — just by typing.
        </p>
        <div className="mt-10 flex gap-4">
          <Button size="lg" asChild>
            <Link href="/login">Get Started</Link>
          </Button>
          <Button variant="outline" size="lg" asChild>
            <Link href="/#features">Learn More</Link>
          </Button>
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Create features section**

Create `src/components/sections/features.tsx`:

```tsx
import { Mic, Plug, Headphones } from "lucide-react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";

const features = [
  {
    icon: Mic,
    title: "Natural Language Control",
    description:
      "Tell your DAW what to do in plain English. No menus, no shortcuts to memorize.",
  },
  {
    icon: Plug,
    title: "Works Inside Your DAW",
    description:
      "A VST3 plugin that lives right in your project. No switching windows.",
  },
  {
    icon: Headphones,
    title: "FL Studio First",
    description:
      "Built for FL Studio from day one. Ableton Live support coming soon.",
  },
];

export function Features() {
  return (
    <section id="features" className="mx-auto max-w-6xl px-6 py-24">
      <div className="text-center">
        <h2 className="text-3xl font-bold tracking-tight">Features</h2>
        <p className="mt-4 text-muted-foreground">
          Everything you need to supercharge your music workflow.
        </p>
      </div>
      <div className="mt-12 grid gap-6 md:grid-cols-3">
        {features.map((feature) => (
          <Card key={feature.title}>
            <CardHeader>
              <div className="mb-2 flex size-10 items-center justify-center rounded-lg bg-muted">
                <feature.icon className="size-5 text-foreground" />
              </div>
              <CardTitle>{feature.title}</CardTitle>
              <CardDescription>{feature.description}</CardDescription>
            </CardHeader>
          </Card>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Create pricing section**

Create `src/components/sections/pricing.tsx`:

```tsx
"use client";

import { useState } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import Link from "next/link";

const plans = [
  {
    name: "Pro",
    monthlyPrice: 19,
    yearlyPrice: 15,
    description: "For individual musicians and producers",
    features: [
      "Unlimited AI commands",
      "All DAW integrations",
      "Priority support",
      "Early access to new features",
    ],
  },
  {
    name: "Studio",
    monthlyPrice: 49,
    yearlyPrice: 39,
    description: "For teams and professional studios",
    features: [
      "Everything in Pro",
      "Team workspace",
      "Custom model selection",
      "Dedicated support & SLA",
      "Analytics dashboard",
    ],
  },
];

export function Pricing() {
  const [annual, setAnnual] = useState(false);

  return (
    <section id="pricing" className="mx-auto max-w-6xl px-6 py-24">
      <div className="text-center">
        <h2 className="text-3xl font-bold tracking-tight">Pricing</h2>
        <p className="mt-4 text-muted-foreground">
          Start free, upgrade when you&apos;re ready.
        </p>
        <div className="mt-6 flex items-center justify-center gap-3">
          <Label
            htmlFor="billing-toggle"
            className="text-sm text-muted-foreground"
          >
            Monthly
          </Label>
          <Switch
            id="billing-toggle"
            checked={annual}
            onCheckedChange={setAnnual}
          />
          <Label
            htmlFor="billing-toggle"
            className="text-sm text-muted-foreground"
          >
            Annual
          </Label>
        </div>
      </div>
      <div className="mx-auto mt-12 grid max-w-3xl gap-6 md:grid-cols-2">
        {plans.map((plan) => {
          const price = annual ? plan.yearlyPrice : plan.monthlyPrice;
          return (
            <Card key={plan.name}>
              <CardHeader>
                <CardTitle className="text-xl">{plan.name}</CardTitle>
                <CardDescription>{plan.description}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div>
                  <span className="text-4xl font-bold">${price}</span>
                  <span className="text-muted-foreground">
                    /month{annual ? ", billed annually" : ""}
                  </span>
                </div>
                <Button className="w-full" asChild>
                  <Link href="/login">Get Started</Link>
                </Button>
                <ul className="space-y-3">
                  {plan.features.map((feature) => (
                    <li key={feature} className="flex items-center gap-3 text-sm">
                      <Check className="size-4 text-muted-foreground" />
                      {feature}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          );
        })}
      </div>
      <p className="mt-8 text-center text-xs text-muted-foreground">
        Data encrypted at rest with AES-256 and in transit with TLS 1.2+.
      </p>
    </section>
  );
}
```

- [ ] **Step 4: Update the landing page to use sections**

Replace `src/app/(marketing)/page.tsx` with:

```tsx
import { Hero } from "@/components/sections/hero";
import { Features } from "@/components/sections/features";
import { Pricing } from "@/components/sections/pricing";

export default function HomePage() {
  return (
    <>
      <Hero />
      <Features />
      <Pricing />
    </>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add src/components/sections/ src/app/\(marketing\)/page.tsx
git commit -m "feat: redesign landing page with hero, features, and pricing sections"
```

---

## Task 8: Redesign login page

**Files:**
- Modify: `src/app/login/page.tsx`

- [ ] **Step 1: Replace login page**

Replace `src/app/login/page.tsx` with:

```tsx
export const dynamic = "force-dynamic";

import { signIn } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export default function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ callbackUrl?: string; context?: string }>;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/50 px-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 text-2xl font-bold tracking-tight">
            Studio AI
          </div>
          <CardTitle className="text-xl">Welcome back</CardTitle>
          <CardDescription>Sign in to your account</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form
            action={async () => {
              "use server";
              const params = await searchParams;
              await signIn("google", {
                redirectTo: params.callbackUrl ?? "/dashboard",
              });
            }}
          >
            <Button variant="outline" type="submit" className="w-full">
              <svg className="mr-2 size-4" viewBox="0 0 24 24">
                <path
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
                  fill="#4285F4"
                />
                <path
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  fill="#34A853"
                />
                <path
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                  fill="#FBBC05"
                />
                <path
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                  fill="#EA4335"
                />
              </svg>
              Continue with Google
            </Button>
          </form>
          <div className="flex items-center gap-4">
            <Separator className="flex-1" />
            <span className="text-xs text-muted-foreground">or</span>
            <Separator className="flex-1" />
          </div>
          <p className="text-center text-xs text-muted-foreground">
            By continuing, you agree to our Terms of Service and Privacy Policy.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
```

Changes from existing:
- Added muted background (`bg-muted/50`)
- Added Google logo SVG
- Changed button text to "Continue with Google"
- Added separator with "or" divider
- Added terms/privacy text
- Better card structure with logo, title, description

- [ ] **Step 2: Commit**

```bash
git add src/app/login/page.tsx
git commit -m "feat: redesign login page with Google logo and Apple-inspired layout"
```

---

## Task 9: Redesign dashboard sidebar

**Files:**
- Modify: `src/components/layout/dashboard-sidebar.tsx`

- [ ] **Step 1: Replace dashboard sidebar**

Replace `src/components/layout/dashboard-sidebar.tsx` with:

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOutAction } from "@/lib/auth-actions";
import {
  LayoutDashboard,
  FolderOpen,
  CreditCard,
  Settings,
  LogOut,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

const navItems = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Projects", href: "/dashboard/projects", icon: FolderOpen },
  { label: "Billing", href: "/dashboard/billing", icon: CreditCard },
  { label: "Settings", href: "/dashboard/settings", icon: Settings },
];

export function DashboardSidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-64 flex-col border-r bg-sidebar">
      <div className="flex h-16 items-center px-6">
        <Link
          href="/dashboard"
          className="text-lg font-bold tracking-tight text-sidebar-foreground"
        >
          Studio AI
        </Link>
      </div>
      <Separator />
      <nav className="flex-1 space-y-1 p-3">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              )}
            >
              <item.icon className="size-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <Separator />
      <div className="p-3">
        <form action={signOutAction}>
          <Button
            type="submit"
            variant="ghost"
            className="w-full justify-start gap-3 text-sidebar-foreground/70"
          >
            <LogOut className="size-4" />
            Sign out
          </Button>
        </form>
      </div>
    </aside>
  );
}
```

Changes from existing:
- Added Lucide icons for each nav item
- Used sidebar theme tokens (`bg-sidebar`, `text-sidebar-foreground`)
- Used `cn()` for active state classes
- Added Separator between sections
- Used shadcn Button for sign out
- Improved spacing and rounded corners

- [ ] **Step 2: Commit**

```bash
git add src/components/layout/dashboard-sidebar.tsx
git commit -m "feat: redesign dashboard sidebar with icons and sidebar theme tokens"
```

---

## Task 10: Create dashboard topbar

**Files:**
- Create: `src/components/layout/dashboard-topbar.tsx`

- [ ] **Step 1: Create topbar component**

Create `src/components/layout/dashboard-topbar.tsx`:

```tsx
import { auth } from "@/lib/auth";
import { signOutAction } from "@/lib/auth-actions";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { LogOut, Settings } from "lucide-react";
import Link from "next/link";

export async function DashboardTopbar({ title }: { title?: string }) {
  const session = await auth();
  const user = session?.user;
  const initials = user?.name
    ? user.name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
        .slice(0, 2)
    : "U";

  return (
    <header className="flex h-16 items-center justify-between border-b px-6">
      <h1 className="text-lg font-semibold tracking-tight">
        {title ?? "Dashboard"}
      </h1>
      <div className="flex items-center gap-2">
        <ThemeToggle />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="relative size-8 rounded-full">
              <Avatar className="size-8">
                <AvatarImage
                  src={user?.image ?? undefined}
                  alt={user?.name ?? "User"}
                />
                <AvatarFallback className="text-xs">{initials}</AvatarFallback>
              </Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <div className="px-2 py-1.5">
              <p className="text-sm font-medium">{user?.name ?? "User"}</p>
              <p className="text-xs text-muted-foreground">
                {user?.email ?? ""}
              </p>
            </div>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <Link href="/dashboard/settings" className="cursor-pointer">
                <Settings className="mr-2 size-4" />
                Settings
              </Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <form action={signOutAction} className="w-full">
                <button
                  type="submit"
                  className="flex w-full items-center text-sm"
                >
                  <LogOut className="mr-2 size-4" />
                  Sign out
                </button>
              </form>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add src/components/layout/dashboard-topbar.tsx
git commit -m "feat: add dashboard topbar with user avatar dropdown and theme toggle"
```

---

## Task 11: Update dashboard layout with topbar and responsive sidebar

**Files:**
- Modify: `src/app/(dashboard)/layout.tsx`

- [ ] **Step 1: Replace dashboard layout**

Replace `src/app/(dashboard)/layout.tsx` with:

```tsx
import { auth } from "@/lib/auth";
import { redirect } from "next/navigation";
import { DashboardSidebar } from "@/components/layout/dashboard-sidebar";
import { DashboardTopbar } from "@/components/layout/dashboard-topbar";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  if (!session) {
    redirect("/login");
  }

  return (
    <div className="flex h-screen">
      <div className="hidden md:block">
        <DashboardSidebar />
      </div>
      <div className="flex flex-1 flex-col overflow-hidden">
        <DashboardTopbar />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-4xl px-6 py-8">{children}</div>
        </main>
      </div>
    </div>
  );
}
```

Changes from existing:
- Added `DashboardTopbar`
- Wrapped sidebar in responsive `hidden md:block`
- Added max-width container for content (`max-w-4xl`)
- Added proper overflow handling

- [ ] **Step 2: Commit**

```bash
git add src/app/\(dashboard\)/layout.tsx
git commit -m "feat: update dashboard layout with topbar and responsive sidebar"
```

---

## Task 12: Redesign dashboard home page

**Files:**
- Modify: `src/app/(dashboard)/dashboard/page.tsx`

- [ ] **Step 1: Replace dashboard page**

Replace `src/app/(dashboard)/dashboard/page.tsx` with:

```tsx
import { auth } from "@/lib/auth";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CreditCard, Settings, Download } from "lucide-react";

export default async function DashboardPage() {
  const session = await auth();

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">
          Welcome back, {session?.user?.name?.split(" ")[0] ?? "there"}
        </h1>
        <p className="mt-1 text-muted-foreground">
          Manage your account and subscription.
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardDescription>Subscription</CardDescription>
            <CardTitle className="flex items-center gap-2">
              Free
              <Badge variant="secondary">Current</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Button variant="outline" size="sm" asChild>
              <Link href="/dashboard/billing">Upgrade</Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardDescription>Plugin Status</CardDescription>
            <CardTitle className="flex items-center gap-2">
              Offline
              <Badge variant="outline">Disconnected</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Button variant="outline" size="sm" asChild>
              <Link href="/dashboard/settings">
                <Download className="mr-2 size-4" />
                Download
              </Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardDescription>Projects</CardDescription>
            <CardTitle>0</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Projects appear here when you use the plugin.
            </p>
          </CardContent>
        </Card>
      </div>

      <div>
        <h2 className="mb-4 text-lg font-semibold tracking-tight">
          Quick Actions
        </h2>
        <div className="flex flex-wrap gap-3">
          <Button variant="outline" asChild>
            <Link href="/dashboard/settings">
              <Settings className="mr-2 size-4" />
              Settings
            </Link>
          </Button>
          <Button variant="outline" asChild>
            <Link href="/dashboard/billing">
              <CreditCard className="mr-2 size-4" />
              Billing
            </Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add src/app/\(dashboard\)/dashboard/page.tsx
git commit -m "feat: redesign dashboard home with status cards and quick actions"
```

---

## Task 13: Redesign billing page

**Files:**
- Modify: `src/app/(dashboard)/dashboard/billing/page.tsx`

- [ ] **Step 1: Replace billing page**

Replace `src/app/(dashboard)/dashboard/billing/page.tsx` with:

```tsx
"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";

const plans = [
  {
    key: "pro" as const,
    name: "Pro",
    monthlyPrice: 19,
    yearlyPrice: 15,
    description: "For individual musicians and producers",
    features: [
      "Unlimited AI commands",
      "All DAW integrations",
      "Priority support",
      "Early access to new features",
    ],
  },
  {
    key: "studio" as const,
    name: "Studio",
    monthlyPrice: 49,
    yearlyPrice: 39,
    description: "For teams and professional studios",
    features: [
      "Everything in Pro",
      "Team workspace",
      "Custom model selection",
      "Dedicated support & SLA",
      "Analytics dashboard",
    ],
  },
];

export default function BillingPage() {
  const [loading, setLoading] = useState<string | null>(null);
  const [annual, setAnnual] = useState(false);
  const searchParams = useSearchParams();
  const success = searchParams.get("success");
  const canceled = searchParams.get("canceled");

  async function handleCheckout(plan: "pro" | "studio") {
    setLoading(plan);
    try {
      const res = await fetch("/api/stripe/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan }),
      });
      const data = await res.json();
      if (data.url) {
        window.location.href = data.url;
      }
    } catch (error) {
      console.error("Checkout error:", error);
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Billing</h1>
        <p className="mt-1 text-muted-foreground">
          Manage your subscription and billing.
        </p>
      </div>

      {success && (
        <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-300">
          Subscription activated successfully.
        </div>
      )}
      {canceled && (
        <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4 text-sm text-yellow-800 dark:border-yellow-800 dark:bg-yellow-950 dark:text-yellow-300">
          Checkout was canceled.
        </div>
      )}

      <Card>
        <CardHeader>
          <CardDescription>Current plan</CardDescription>
          <CardTitle className="flex items-center gap-2">
            Free
            <Badge variant="secondary">Active</Badge>
          </CardTitle>
        </CardHeader>
      </Card>

      <Separator />

      <div>
        <h2 className="text-lg font-semibold tracking-tight">Upgrade</h2>
        <div className="mt-4 flex items-center gap-3">
          <Label
            htmlFor="billing-toggle"
            className="text-sm text-muted-foreground"
          >
            Monthly
          </Label>
          <Switch
            id="billing-toggle"
            checked={annual}
            onCheckedChange={setAnnual}
          />
          <Label
            htmlFor="billing-toggle"
            className="text-sm text-muted-foreground"
          >
            Annual
          </Label>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {plans.map((plan) => {
          const price = annual ? plan.yearlyPrice : plan.monthlyPrice;
          return (
            <Card key={plan.key}>
              <CardHeader>
                <CardTitle className="text-xl">{plan.name}</CardTitle>
                <CardDescription>{plan.description}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div>
                  <span className="text-4xl font-bold">${price}</span>
                  <span className="text-muted-foreground">
                    /month{annual ? ", billed annually" : ""}
                  </span>
                </div>
                <Button
                  onClick={() => handleCheckout(plan.key)}
                  disabled={loading !== null}
                  className="w-full"
                >
                  {loading === plan.key
                    ? "Redirecting..."
                    : `Subscribe to ${plan.name}`}
                </Button>
                <ul className="space-y-3">
                  {plan.features.map((feature) => (
                    <li
                      key={feature}
                      className="flex items-center gap-3 text-sm"
                    >
                      <Check className="size-4 text-muted-foreground" />
                      {feature}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <p className="text-center text-xs text-muted-foreground">
        Data encrypted at rest with AES-256 and in transit with TLS 1.2+.
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add src/app/\(dashboard\)/dashboard/billing/page.tsx
git commit -m "feat: redesign billing page with annual toggle and feature checklists"
```

---

## Task 14: Create settings page

**Files:**
- Create: `src/app/(dashboard)/dashboard/settings/page.tsx`

- [ ] **Step 1: Create settings page**

Create `src/app/(dashboard)/dashboard/settings/page.tsx`:

```tsx
import { auth } from "@/lib/auth";
import { signOutAction } from "@/lib/auth-actions";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ThemeToggle } from "@/components/layout/theme-toggle";

export default async function SettingsPage() {
  const session = await auth();
  const user = session?.user;
  const initials = user?.name
    ? user.name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
        .slice(0, 2)
    : "U";

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="mt-1 text-muted-foreground">
          Manage your profile and preferences.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Profile</CardTitle>
          <CardDescription>Your account information from Google.</CardDescription>
        </CardHeader>
        <CardContent className="flex items-center gap-4">
          <Avatar className="size-16">
            <AvatarImage
              src={user?.image ?? undefined}
              alt={user?.name ?? "User"}
            />
            <AvatarFallback>{initials}</AvatarFallback>
          </Avatar>
          <div>
            <p className="font-medium">{user?.name ?? "User"}</p>
            <p className="text-sm text-muted-foreground">
              {user?.email ?? ""}
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Appearance</CardTitle>
          <CardDescription>
            Customize the look and feel of the app.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Theme</p>
            <p className="text-sm text-muted-foreground">
              Select light, dark, or system theme.
            </p>
          </div>
          <ThemeToggle />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Account</CardTitle>
          <CardDescription>Manage your account.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Separator />
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Sign out</p>
              <p className="text-sm text-muted-foreground">
                Sign out of your account on this device.
              </p>
            </div>
            <form action={signOutAction}>
              <Button variant="outline" type="submit">
                Sign out
              </Button>
            </form>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add src/app/\(dashboard\)/dashboard/settings/page.tsx
git commit -m "feat: add settings page with profile, appearance, and account sections"
```

---

## Task 15: Clean up deleted files and verify build

**Files:**
- Delete: `src/components/ui/button-variants.ts`

- [ ] **Step 1: Delete old button-variants file**

Check if `button-variants.ts` still exists (it should have been removed in Task 1, but verify):

```bash
ls src/components/ui/button-variants.ts 2>/dev/null && echo "EXISTS - delete it" || echo "Already removed"
```

If it exists:
```bash
rm src/components/ui/button-variants.ts
```

- [ ] **Step 2: Check for any remaining imports of old components**

```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
grep -r "button-variants" src/ --include="*.tsx" --include="*.ts"
grep -r "@base-ui/react" src/ --include="*.tsx" --include="*.ts"
```

Expected: No matches in browser-facing files. Plugin files (`src/app/(plugin)/**`) may still reference old components — that's fine, they're untouched.

If any browser-facing files still import `button-variants` or `@base-ui/react`, update their imports to use shadcn components instead.

- [ ] **Step 3: Run the build**

```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
pnpm build
```

Expected: Build succeeds with no errors.

- [ ] **Step 4: Commit any cleanup**

```bash
git add -A
git commit -m "chore: clean up old component references and verify build"
```

---

## Task 16: Final visual verification

- [ ] **Step 1: Start dev server and check all pages**

```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
pnpm dev
```

Manually check in browser:
- `http://localhost:3000` — Landing page (hero, features, pricing)
- `http://localhost:3000/login` — Login page
- `http://localhost:3000/dashboard` — Dashboard home (requires auth)
- `http://localhost:3000/dashboard/billing` — Billing page
- `http://localhost:3000/dashboard/settings` — Settings page
- Theme toggle: light → dark → system on each page
- Mobile responsive: resize browser to check sidebar collapse

- [ ] **Step 2: Commit final state**

```bash
git add -A
git commit -m "feat: complete website redesign with shadcn and monochrome theme

Redesigned landing page, dashboard, login, billing, and settings
using shadcn/ui components. Added light/dark/system theme support
with next-themes. Apple/Sana-inspired monochrome visual design."
```
