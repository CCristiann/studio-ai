"use client";

import { useState } from "react";
import { Check } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
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
                <Link href="/login" className={cn(buttonVariants(), "w-full")}>
                  Get Started
                </Link>
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
