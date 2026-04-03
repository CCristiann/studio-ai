import NextAuth from "next-auth";
import { SupabaseAdapter } from "@auth/supabase-adapter";
import Google from "next-auth/providers/google";
import { SignJWT } from "jose";

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
  pages: {
    signIn: "/login",
  },
});
