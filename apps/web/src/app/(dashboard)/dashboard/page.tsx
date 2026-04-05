import { auth } from "@/lib/auth";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button-variants";
import { CreditCard, Settings, Download } from "lucide-react";
import { cn } from "@/lib/utils";

export default async function DashboardPage() {
  const session = await auth();

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">
          Welcome back, {session?.user?.name?.split(" ")[0] ?? "there"}
        </h1>
        <p className="mt-1 text-muted-foreground">
          Manage your account and subscription.
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardDescription>Subscription</CardDescription>
            <CardTitle className="flex items-center gap-2">
              Free
              <Badge variant="secondary">Current</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Link href="/dashboard/billing" className={cn(buttonVariants({ variant: "outline", size: "sm" }))}>
              Upgrade
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardDescription>Plugin Status</CardDescription>
            <CardTitle className="flex items-center gap-2">
              Offline
              <Badge variant="outline">Disconnected</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Link href="/dashboard/settings" className={cn(buttonVariants({ variant: "outline", size: "sm" }))}>
              <Download className="mr-2 size-4" />
              Download
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardDescription>Projects</CardDescription>
            <CardTitle>0</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Projects appear here when you use the plugin.
            </p>
          </CardContent>
        </Card>
      </div>

      <div>
        <h2 className="mb-4 text-lg font-semibold tracking-tight">
          Quick Actions
        </h2>
        <div className="flex flex-wrap gap-3">
          <Link href="/dashboard/settings" className={cn(buttonVariants({ variant: "outline" }))}>
            <Settings className="mr-2 size-4" />
            Settings
          </Link>
          <Link href="/dashboard/billing" className={cn(buttonVariants({ variant: "outline" }))}>
            <CreditCard className="mr-2 size-4" />
            Billing
          </Link>
        </div>
      </div>
    </div>
  );
}
