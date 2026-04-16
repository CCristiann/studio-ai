import NextAuth from "next-auth";
import { SupabaseAdapter } from "@auth/supabase-adapter";
import Google from "next-auth/providers/google";
import { SignJWT } from "jose";
import { recordAuthEvent } from "./auth-events";

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [Google],
  adapter: SupabaseAdapter({
    url: process.env.NEXT_PUBLIC_SUPABASE_URL!,
    secret: process.env.SUPABASE_SERVICE_ROLE_KEY!,
  }),
  callbacks: {
    async session({ session, user }) {
      const signingSecret = process.env.SUPABASE_JWT_SECRET;
      if (signingSecret) {
        const secret = new TextEncoder().encode(signingSecret);
        session.supabaseAccessToken = await new SignJWT({
          aud: "authenticated",
          sub: user.id,
          email: user.email,
          role: "authenticated",
        })
          .setProtectedHeader({ alg: "HS256" })
          .setExpirationTime(new Date(session.expires))
          .sign(secret);
      }
      session.userId = user.id;
      return session;
    },
  },
  events: {
    // Fires once per successful sign-in. `isNewUser` tells us whether this
    // was a first-time vs returning login — useful for noise filtering.
    async signIn({ user, account, isNewUser }) {
      if (!user?.id) return;
      await recordAuthEvent({
        type: "login_succeeded",
        userId: user.id,
        success: true,
        metadata: {
          provider: account?.provider ?? "unknown",
          isNewUser: Boolean(isNewUser),
        },
      });
    },
  },
  pages: {
    signIn: "/login",
  },
});
