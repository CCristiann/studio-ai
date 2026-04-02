import Link from "next/link";
import { buttonVariants } from "@/components/ui/button-variants";
import { cn } from "@/lib/utils";

export default function HomePage() {
  return (
    <div className="flex flex-col items-center">
      {/* Hero */}
      <section className="flex flex-col items-center gap-6 px-4 py-24 text-center">
        <h1 className="max-w-3xl text-5xl font-bold tracking-tight">
          Control Your DAW with Natural Language
        </h1>
        <p className="max-w-xl text-lg text-muted-foreground">
          Studio AI is an AI-powered agent that lets musicians organize and
          control their Digital Audio Workstation through conversation. Set BPM,
          add tracks, manage your project — just by typing.
        </p>
        <div className="flex gap-4">
          <Link
            href="/login"
            className={cn(buttonVariants({ size: "lg" }))}
          >
            Get Started Free
          </Link>
          <Link
            href="/#features"
            className={cn(buttonVariants({ variant: "outline", size: "lg" }))}
          >
            Learn More
          </Link>
        </div>
      </section>

      {/* Features placeholder */}
      <section id="features" className="w-full max-w-5xl px-4 py-16">
        <h2 className="mb-8 text-center text-3xl font-bold">Features</h2>
        <div className="grid gap-8 md:grid-cols-3">
          <div className="rounded-lg border p-6">
            <h3 className="mb-2 text-lg font-semibold">Natural Language Control</h3>
            <p className="text-sm text-muted-foreground">
              Tell your DAW what to do in plain English. No menus, no shortcuts to memorize.
            </p>
          </div>
          <div className="rounded-lg border p-6">
            <h3 className="mb-2 text-lg font-semibold">Works Inside Your DAW</h3>
            <p className="text-sm text-muted-foreground">
              A VST3 plugin that lives right in your project. No switching windows.
            </p>
          </div>
          <div className="rounded-lg border p-6">
            <h3 className="mb-2 text-lg font-semibold">FL Studio First</h3>
            <p className="text-sm text-muted-foreground">
              Built for FL Studio from day one. Ableton Live support coming soon.
            </p>
          </div>
        </div>
      </section>

      {/* Pricing placeholder */}
      <section id="pricing" className="w-full max-w-3xl px-4 py-16">
        <h2 className="mb-8 text-center text-3xl font-bold">Pricing</h2>
        <div className="grid gap-8 md:grid-cols-3">
          <div className="rounded-lg border p-6 text-center">
            <h3 className="text-lg font-semibold">Free</h3>
            <p className="my-4 text-3xl font-bold">$0</p>
            <p className="text-sm text-muted-foreground">Basic DAW commands</p>
          </div>
          <div className="rounded-lg border-2 border-primary p-6 text-center">
            <h3 className="text-lg font-semibold">Pro</h3>
            <p className="my-4 text-3xl font-bold">$19/mo</p>
            <p className="text-sm text-muted-foreground">Unlimited AI commands</p>
          </div>
          <div className="rounded-lg border p-6 text-center">
            <h3 className="text-lg font-semibold">Studio</h3>
            <p className="my-4 text-3xl font-bold">$49/mo</p>
            <p className="text-sm text-muted-foreground">Team features + priority</p>
          </div>
        </div>
      </section>
    </div>
  );
}
