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
