import { auth } from "@/lib/auth";
import { redirect } from "next/navigation";
import { PluginChat } from "./plugin-chat";

export default async function PluginPage() {
  const session = await auth();

  if (!session?.userId) {
    redirect("/login");
  }

  return <PluginChat />;
}
