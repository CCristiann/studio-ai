"use client";

import { useActionState } from "react";
import { verifyUserCode } from "./actions";

export default function LinkPage() {
  const [state, formAction, isPending] = useActionState(verifyUserCode, {});

  if (state.success) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="w-full max-w-sm space-y-4 text-center">
          <h1 className="text-2xl font-bold text-green-600">Plugin Authorized</h1>
          <p className="text-muted-foreground">
            You can close this tab and return to FL Studio.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="w-full max-w-sm space-y-6 text-center">
        <div className="space-y-2">
          <h1 className="text-2xl font-bold">Studio AI</h1>
          <p className="text-muted-foreground">
            Enter the code shown in your FL Studio plugin.
          </p>
        </div>

        <form action={formAction} className="space-y-4">
          <input
            name="code"
            type="text"
            autoComplete="off"
            autoFocus
            maxLength={7}
            placeholder="XXX-XXX"
            className="w-full rounded-md border bg-background px-4 py-3 text-center text-2xl font-mono tracking-widest uppercase placeholder:text-muted-foreground/40"
          />
          <button
            type="submit"
            disabled={isPending}
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {isPending ? "Verifying..." : "Authorize Plugin"}
          </button>
        </form>

        {state.error && (
          <p className="text-sm text-destructive">{state.error}</p>
        )}

        <p className="text-xs text-muted-foreground">
          This links your FL Studio plugin to your Studio AI account.
        </p>
      </div>
    </div>
  );
}
