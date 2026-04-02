import "next-auth";

declare module "next-auth" {
  interface Session {
    supabaseAccessToken?: string;
    userId?: string;
  }
}
