# Website Redesign — shadcn + Apple/Sana-Inspired Theme

**Date:** 2026-04-05
**Status:** Approved
**Scope:** Browser views only — landing page, dashboard, login. Plugin routes untouched.

---

## 1. Goals

- Redesign the web app using shadcn/ui components with latest Tailwind CSS v4
- Apply a monochrome, semi-Apple/Sana-inspired visual theme
- Support light and dark mode (system default + manual toggle with persistence)
- Create reusable components with optimized folder organization
- Leave plugin routes, API routes, and all backend logic untouched

---

## 2. Folder Structure

```
src/
├── app/
│   ├── (marketing)/
│   │   ├── layout.tsx              # Marketing layout (header + footer)
│   │   └── page.tsx                # Landing page (hero, features, pricing)
│   ├── (dashboard)/
│   │   ├── layout.tsx              # Dashboard layout (sidebar + topbar)
│   │   └── dashboard/
│   │       ├── page.tsx            # Overview / home
│   │       ├── billing/
│   │       │   └── page.tsx        # Billing & subscription management
│   │       └── settings/
│   │           └── page.tsx        # User settings (profile, theme preference)
│   ├── (plugin)/                   # UNTOUCHED — future redesign
│   │   ├── layout.tsx
│   │   └── plugin/
│   │       ├── page.tsx
│   │       ├── plugin-chat.tsx
│   │       └── plugin-login.tsx
│   ├── login/
│   │   └── page.tsx                # Google OAuth login
│   ├── link/                       # UNTOUCHED
│   │   ├── page.tsx
│   │   └── actions.ts
│   ├── api/                        # UNTOUCHED — all existing API routes
│   ├── globals.css                 # Tailwind + shadcn monochrome theme
│   └── layout.tsx                  # Root layout (fonts, ThemeProvider, metadata)
├── components/
│   ├── ui/                         # shadcn primitives (installed via CLI)
│   ├── layout/
│   │   ├── marketing-header.tsx    # Sticky header with nav, theme toggle, CTAs
│   │   ├── marketing-footer.tsx    # Footer with links and copyright
│   │   ├── dashboard-sidebar.tsx   # Fixed sidebar with nav items
│   │   ├── dashboard-topbar.tsx    # Page title, user dropdown, theme toggle
│   │   └── theme-toggle.tsx        # Sun/moon toggle (shared)
│   └── sections/
│       ├── hero.tsx                # Landing hero section
│       ├── features.tsx            # Landing features grid
│       └── pricing.tsx             # Landing pricing cards
├── hooks/
│   ├── use-plugin-context.ts       # Existing — untouched
│   └── use-theme.ts                # Theme preference hook (if needed beyond next-themes)
└── lib/
    ├── utils.ts                    # Existing cn() utility
    └── ...                         # All existing lib files untouched
```

### Design decisions

- **`sections/`** — Landing page compositions extracted for readability, not for cross-page reuse.
- **`layout/`** — Truly shared layout components used across route groups.
- **`ui/`** — Pure shadcn primitives, no custom wrappers.
- **New `settings/` route** — For user profile and theme preference management.

---

## 3. Theme Design

### 3.1 Color Palette (oklch, monochrome)

**Light mode:**

| Token | Value | Usage |
|---|---|---|
| `--background` | `oklch(1 0 0)` | Page background (pure white) |
| `--foreground` | `oklch(0.145 0 0)` | Primary text (near-black) |
| `--card` | `oklch(1 0 0)` | Card backgrounds |
| `--card-foreground` | `oklch(0.145 0 0)` | Card text |
| `--muted` | `oklch(0.97 0 0)` | Muted backgrounds |
| `--muted-foreground` | `oklch(0.556 0 0)` | Secondary text |
| `--border` | `oklch(0.922 0 0)` | Subtle borders |
| `--primary` | `oklch(0.145 0 0)` | Black primary buttons |
| `--primary-foreground` | `oklch(0.985 0 0)` | White text on primary |
| `--secondary` | `oklch(0.965 0 0)` | Light gray secondary bg |
| `--secondary-foreground` | `oklch(0.205 0 0)` | Dark text on secondary |
| `--accent` | `oklch(0.965 0 0)` | Accent backgrounds |
| `--accent-foreground` | `oklch(0.205 0 0)` | Accent text |
| `--destructive` | `oklch(0.577 0.245 27.325)` | Error/destructive red |
| `--ring` | `oklch(0.708 0 0)` | Focus ring (gray) |

**Dark mode:**

| Token | Value | Usage |
|---|---|---|
| `--background` | `oklch(0.145 0 0)` | Page background (near-black) |
| `--foreground` | `oklch(0.985 0 0)` | Primary text (white) |
| `--card` | `oklch(0.205 0 0)` | Card backgrounds |
| `--card-foreground` | `oklch(0.985 0 0)` | Card text |
| `--muted` | `oklch(0.269 0 0)` | Muted backgrounds |
| `--muted-foreground` | `oklch(0.708 0 0)` | Secondary text |
| `--border` | `oklch(0.3 0 0)` | Subtle borders |
| `--primary` | `oklch(0.985 0 0)` | White primary buttons |
| `--primary-foreground` | `oklch(0.145 0 0)` | Black text on primary |
| `--secondary` | `oklch(0.269 0 0)` | Dark secondary bg |
| `--secondary-foreground` | `oklch(0.985 0 0)` | Light text on secondary |
| `--accent` | `oklch(0.269 0 0)` | Accent backgrounds |
| `--accent-foreground` | `oklch(0.985 0 0)` | Accent text |
| `--destructive` | `oklch(0.577 0.245 27.325)` | Error/destructive red |
| `--ring` | `oklch(0.556 0 0)` | Focus ring |

### 3.2 Typography

- **Font:** Geist Sans (already loaded)
- **Headings:** Bold (700), tracking-tight (-0.02em)
- **Body:** Regular (400), normal tracking
- **Hero headline:** 4rem–5rem, bold
- **Generous line heights** for readability

### 3.3 Spacing & Radius

- **Border radius:** `0.625rem` default (medium rounded, not pill)
- **Spacing:** Generous Apple-like whitespace throughout
- **Card shadows:** None in light mode (border-only), optional subtle shadow in dark

### 3.4 Buttons

- **Primary:** Solid black (light) / white (dark), medium radius, subtle opacity hover
- **Secondary/Ghost:** Transparent with hover background
- **No gradients, no colored accents**

---

## 4. shadcn Components to Install

| Component | Usage |
|---|---|
| `button` | CTAs, nav actions, form submits |
| `card` | Feature cards, pricing cards, dashboard panels |
| `input` | Settings forms, login form |
| `label` | Form labels |
| `badge` | Plan badges, status indicators |
| `separator` | Section dividers |
| `avatar` | User profile in sidebar/topbar |
| `dropdown-menu` | User menu in topbar |
| `switch` | Annual/monthly billing toggle |
| `dialog` | Confirmation modals |
| `sheet` | Mobile sidebar |
| `navigation-menu` | Marketing header nav |

---

## 5. Layout Designs

### 5.1 Marketing Layout

- **Header:** Sticky, backdrop-blur on scroll, subtle bottom border. Contains: logo (left), nav links center (Features, Pricing), actions right (theme toggle, Sign In ghost button, Get Started primary button).
- **Content:** Full-width, max-width container (~1200px), generous horizontal padding.
- **Footer:** Simple — logo, link groups, copyright.

### 5.2 Dashboard Layout

- **Sidebar:** Fixed left, 256px wide. Nav items: Dashboard, Projects, Billing, Settings. User avatar + sign out at bottom.
- **Topbar:** Page title (left), theme toggle + user dropdown (right).
- **Content:** Max-width ~960px, centered, with padding.
- **Mobile:** Sidebar hidden, hamburger in topbar opens Sheet overlay.

### 5.3 Login Page

- No marketing header/footer.
- Centered vertically and horizontally.
- Single card: logo, heading ("Welcome back"), Google sign-in button, email input, "Continue" button.
- Subtle muted background.

---

## 6. Page Designs

### 6.1 Landing Page (`(marketing)/page.tsx`)

Assembles three sections:

**Hero:**
- Large bold headline (e.g., "AI-powered music production")
- Subtitle paragraph
- Two CTA buttons: "Get Started" (primary), "Learn More" (secondary/ghost)
- Product screenshot or mockup visual (right side on desktop, below on mobile)

**Features:**
- Section heading: "Features"
- 3 cards in a responsive grid (1 col mobile, 3 col desktop)
- Each card: icon (Lucide), title, description
- Clean card styling with subtle border

**Pricing:**
- Section heading: "Pricing"
- Annual/monthly toggle (Switch component)
- Two pricing cards side by side:
  - **Pro** ($19/mo): feature checklist with checkmarks
  - **Studio** ($49/mo): feature checklist with checkmarks
- Each card: plan name, price, billing period, CTA button, feature list
- Security/compliance note below (like Sana's ISO/GDPR line)

### 6.2 Login Page (`login/page.tsx`)

- Centered card on muted background
- Logo at top
- "Welcome back" heading, "Sign in to your account" subtitle
- Google sign-in button (outline style with Google icon)
- Divider with "or"
- Email input + "Continue with email" button
- Footer text: terms/privacy links

### 6.3 Dashboard Home (`dashboard/page.tsx`)

- Welcome message with user name from session
- Subscription status card (current plan, renewal date)
- Quick links grid: Settings, Billing, Download Plugin

### 6.4 Billing Page (`dashboard/billing/page.tsx`)

- Current plan display (card with plan name, price, status badge)
- "Manage Subscription" button (Stripe portal redirect)
- Pricing cards (same as landing page pricing section, reuse data)

### 6.5 Settings Page (`dashboard/settings/page.tsx`)

- Profile section: avatar, name, email (read-only from Google)
- Appearance section: theme preference (System / Light / Dark) using a button group or dropdown
- Account section: sign out button, danger zone (future: delete account)

---

## 7. Dark Mode Implementation

- **Library:** `next-themes` (new dependency)
- **Strategy:** Class-based (`.dark` on `<html>`)
- **Default:** System preference
- **Override:** Manual toggle persisted to localStorage
- **ThemeProvider:** Wraps app in root layout with `attribute="class"` and `defaultTheme="system"`
- **ThemeToggle component:** Sun/Moon icon button, cycles System → Light → Dark

---

## 8. New Dependency

| Package | Purpose |
|---|---|
| `next-themes` | Theme management (system detection + manual toggle + localStorage persistence) |

---

## 9. What Is NOT Changing

- All API routes (`/api/*`)
- Plugin routes (`(plugin)/*`)
- Link page (`/link`)
- Middleware logic
- Auth configuration (NextAuth, device flow, plugin JWT)
- Stripe integration logic
- AI chat endpoint
- Database schema
- Shared types package (`@studio-ai/types`)
- Rate limiting
- Relay client

---

## 10. Migration Notes

- Existing `@base-ui/react` button and input components will be replaced by shadcn equivalents
- Existing `button-variants.ts` CVA file will be removed (shadcn buttons have their own variants)
- Existing card component will be replaced by shadcn card
- `components.json` will be updated to reflect new shadcn installation
- Current `globals.css` theme variables will be replaced with monochrome values
