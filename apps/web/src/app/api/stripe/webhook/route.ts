import { NextRequest, NextResponse } from "next/server";
import { stripe } from "@/lib/stripe";
import { createSupabaseServerClient } from "@/lib/supabase";
import type Stripe from "stripe";

export async function POST(req: NextRequest) {
  const body = await req.text();
  const signature = req.headers.get("stripe-signature");

  if (!signature) {
    return NextResponse.json({ error: "Missing signature" }, { status: 400 });
  }

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(
      body,
      signature,
      process.env.STRIPE_WEBHOOK_SECRET!
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    console.error(`Webhook signature verification failed: ${message}`);
    return NextResponse.json({ error: "Invalid signature" }, { status: 400 });
  }

  const supabase = createSupabaseServerClient();

  switch (event.type) {
    case "customer.subscription.created":
    case "customer.subscription.updated": {
      const subscription = event.data.object as Stripe.Subscription;
      const customerId =
        typeof subscription.customer === "string"
          ? subscription.customer
          : subscription.customer.id;

      const plan = determinePlan(subscription);
      const status = mapStatus(subscription.status);

      // Derive period end: use cancel_at if set, otherwise fall back to null
      // Note: current_period_end was removed in Stripe API v2026-03-25.dahlia
      const periodEnd = subscription.cancel_at
        ? new Date(subscription.cancel_at * 1000).toISOString()
        : null;

      await supabase
        .from("subscriptions")
        .update({
          stripe_subscription_id: subscription.id,
          plan,
          status,
          ...(periodEnd ? { current_period_end: periodEnd } : {}),
        })
        .eq("stripe_customer_id", customerId);
      break;
    }

    case "customer.subscription.deleted": {
      const subscription = event.data.object as Stripe.Subscription;
      const customerId =
        typeof subscription.customer === "string"
          ? subscription.customer
          : subscription.customer.id;

      await supabase
        .from("subscriptions")
        .update({
          plan: "free",
          status: "canceled",
          stripe_subscription_id: null,
          current_period_end: null,
        })
        .eq("stripe_customer_id", customerId);
      break;
    }
  }

  return NextResponse.json({ received: true });
}

function determinePlan(subscription: Stripe.Subscription): string {
  const priceId = subscription.items.data[0]?.price?.id;
  if (priceId === process.env.STRIPE_STUDIO_PRICE_ID) return "studio";
  if (priceId === process.env.STRIPE_PRO_PRICE_ID) return "pro";
  return "free";
}

function mapStatus(
  stripeStatus: Stripe.Subscription.Status
): "active" | "canceled" | "past_due" {
  switch (stripeStatus) {
    case "active":
    case "trialing":
      return "active";
    case "past_due":
      return "past_due";
    default:
      return "canceled";
  }
}
