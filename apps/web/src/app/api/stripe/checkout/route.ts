import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { stripe, PLANS } from "@/lib/stripe";
import { createSupabaseServerClient } from "@/lib/supabase";

export async function POST(req: NextRequest) {
  const session = await auth();
  if (!session?.userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await req.json();
  const plan = body.plan as keyof typeof PLANS;

  if (!plan || !PLANS[plan]) {
    return NextResponse.json({ error: "Invalid plan" }, { status: 400 });
  }

  const supabase = createSupabaseServerClient();

  // Check if user already has a Stripe customer
  const { data: subscription } = await supabase
    .from("subscriptions")
    .select("stripe_customer_id")
    .eq("user_id", session.userId)
    .single();

  let customerId = subscription?.stripe_customer_id;

  if (!customerId) {
    // Create Stripe customer
    const customer = await stripe.customers.create({
      email: session.user?.email ?? undefined,
      metadata: { user_id: session.userId },
    });
    customerId = customer.id;

    // Upsert subscription record with customer ID
    await supabase.from("subscriptions").upsert({
      user_id: session.userId,
      stripe_customer_id: customerId,
      plan: "free",
      status: "active",
    });
  }

  // Create checkout session
  const checkoutSession = await stripe.checkout.sessions.create({
    customer: customerId,
    mode: "subscription",
    line_items: [{ price: PLANS[plan].priceId, quantity: 1 }],
    success_url: `${process.env.NEXTAUTH_URL}/dashboard/billing?success=true`,
    cancel_url: `${process.env.NEXTAUTH_URL}/dashboard/billing?canceled=true`,
    metadata: { user_id: session.userId },
  });

  return NextResponse.json({ url: checkoutSession.url });
}
