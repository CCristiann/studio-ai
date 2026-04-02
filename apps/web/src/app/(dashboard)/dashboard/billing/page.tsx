"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const plans = [
  {
    key: "pro" as const,
    name: "Pro",
    price: "$19/mo",
    description: "Unlimited AI commands, priority support",
  },
  {
    key: "studio" as const,
    name: "Studio",
    price: "$49/mo",
    description: "Team features, priority support, early access",
  },
];

export default function BillingPage() {
  const [loading, setLoading] = useState<string | null>(null);
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
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Billing</h1>

      {success && (
        <div className="rounded-md bg-green-50 p-4 text-green-800 dark:bg-green-900/20 dark:text-green-400">
          Subscription activated successfully.
        </div>
      )}
      {canceled && (
        <div className="rounded-md bg-yellow-50 p-4 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400">
          Checkout was canceled.
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        {plans.map((plan) => (
          <Card key={plan.key}>
            <CardHeader>
              <CardTitle>{plan.name}</CardTitle>
              <CardDescription>{plan.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="mb-4 text-3xl font-bold">{plan.price}</p>
              <Button
                onClick={() => handleCheckout(plan.key)}
                disabled={loading !== null}
                className="w-full"
              >
                {loading === plan.key ? "Redirecting..." : `Subscribe to ${plan.name}`}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
