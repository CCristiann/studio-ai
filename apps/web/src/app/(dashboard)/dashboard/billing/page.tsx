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
