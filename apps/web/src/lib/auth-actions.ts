"use server";

import { auth, signOut } from "@/lib/auth";
import { revokePluginTokensForUser } from "@/lib/plugin-auth";

export async function signOutAction() {
  // Revoke all plugin tokens before destroying the session
  const session = await auth();
  if (session?.userId) {
    await revokePluginTokensForUser(session.userId);
  }

  await signOut({ redirectTo: "/login" });
}
