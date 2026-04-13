"use client";

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { MessageSquare, Zap, Sparkles } from "lucide-react";
import { useUpdatePreferences } from '@/hooks/mutations/use-preferences-mutations'

const steps = [
  {
    icon: Sparkles,
    title: "Welcome to Studio AI",
    description:
      "Your AI-powered assistant for music production. Control your DAW with natural language — no menus, no shortcuts to memorize.",
  },
  {
    icon: MessageSquare,
    title: "Talk to Your DAW",
    description:
      'Just type what you want. "Set BPM to 128", "Add a bass track", "Analyze my mix". Studio AI translates your words into DAW actions instantly.',
  },
  {
    icon: Zap,
    title: "Save Quick Actions",
    description:
      "Create presets for commands you use often. One click to set up your favorite beat template, apply sidechain compression, or any workflow you repeat.",
  },
];

export function OnboardingWizard({
  open,
  onComplete,
}: {
  open: boolean;
  onComplete: () => void;
}) {
  const [step, setStep] = useState(0);
  const updatePreferences = useUpdatePreferences()

  // Reset to first step when wizard reopens
  useEffect(() => {
    if (open) setStep(0);
  }, [open]);

  const handleNext = () => {
    if (step < steps.length - 1) {
      setStep(step + 1)
    } else {
      updatePreferences.mutate(
        { onboarding_completed: true },
        { onSuccess: () => onComplete() },
      )
    }
  }

  const current = steps[step];

  return (
    <Dialog open={open} onOpenChange={() => {}}>
      <DialogContent className="max-w-sm border-white/5 bg-[#0a0a0a] sm:rounded-2xl [&>button]:hidden">
        <DialogHeader className="items-center text-center">
          <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-2xl bg-white/[0.05]">
            <current.icon className="h-6 w-6 text-white" />
          </div>
          <DialogTitle className="text-base">{current.title}</DialogTitle>
          <DialogDescription className="text-[13px] leading-relaxed text-[#888]">
            {current.description}
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-between pt-4">
          <div className="flex gap-1.5">
            {steps.map((_, i) => (
              <div
                key={i}
                className={`h-1.5 w-1.5 rounded-full transition-colors ${
                  i === step ? "bg-white" : "bg-white/10"
                }`}
              />
            ))}
          </div>
          <Button
            onClick={handleNext}
            size="sm"
            className="rounded-full px-5"
          >
            {step < steps.length - 1 ? "Next" : "Get Started"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
