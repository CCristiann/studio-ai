import Link from "next/link";
import { buttonVariants } from "@/components/ui/button-variants";
import { cn } from "@/lib/utils";

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
          <Link href="/login" className={cn(buttonVariants({ size: "lg" }))}>
            Get Started
          </Link>
          <Link href="/#features" className={cn(buttonVariants({ variant: "outline", size: "lg" }))}>
            Learn More
          </Link>
        </div>
      </div>
    </section>
  );
}
