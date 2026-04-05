"use client";

import { useEffect, useState, useCallback } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Plus } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

interface Preset {
  id: string;
  name: string;
  description: string | null;
  prompt: string;
}

export function PresetsPanel({
  token,
  onSendPrompt,
}: {
  token: string;
  onSendPrompt: (prompt: string) => void;
}) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newPrompt, setNewPrompt] = useState("");
  const [saving, setSaving] = useState(false);

  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

  const fetchPresets = useCallback(async () => {
    const res = await fetch("/api/plugin/presets", { headers: { Authorization: `Bearer ${token}` } });
    if (res.ok) {
      const data = await res.json();
      setPresets(data.presets);
    }
    setLoading(false);
  }, [token]);

  useEffect(() => {
    fetchPresets();
  }, [fetchPresets]);

  const handleCreate = async () => {
    if (!newName.trim() || !newPrompt.trim()) return;
    setSaving(true);
    const res = await fetch("/api/plugin/presets", {
      method: "POST",
      headers,
      body: JSON.stringify({ name: newName, description: newDescription || null, prompt: newPrompt }),
    });
    if (res.ok) {
      const data = await res.json();
      setPresets((prev) => [...prev, data.preset]);
      setShowCreate(false);
      setNewName("");
      setNewDescription("");
      setNewPrompt("");
    }
    setSaving(false);
  };

  if (loading) {
    return (
      <div className="space-y-2 p-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-14 w-full rounded-xl" />
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5 p-2.5">
      {presets.map((preset) => (
        <button
          key={preset.id}
          onClick={() => onSendPrompt(preset.prompt)}
          className="rounded-xl bg-white/[0.02] px-3.5 py-3 text-left transition-colors hover:bg-white/[0.04]"
        >
          <div className="text-[12.5px] font-medium text-[#c8c8c8]">
            {preset.name}
          </div>
          {preset.description && (
            <div className="mt-0.5 text-[10.5px] text-[#444] line-clamp-1">
              {preset.description}
            </div>
          )}
        </button>
      ))}

      <button
        onClick={() => setShowCreate(true)}
        className="rounded-xl border border-dashed border-white/5 py-3 text-center text-[12px] text-[#333] transition-colors hover:border-white/10 hover:text-[#555]"
      >
        <Plus className="mr-1 inline h-3.5 w-3.5" />
        Create Custom
      </button>

      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Preset</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 pt-2">
            <div>
              <Label htmlFor="preset-name">Name</Label>
              <Input
                id="preset-name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Lo-fi Beat Setup"
              />
            </div>
            <div>
              <Label htmlFor="preset-desc">Description (optional)</Label>
              <Input
                id="preset-desc"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                placeholder="Set BPM, add drums, bass, keys"
              />
            </div>
            <div>
              <Label htmlFor="preset-prompt">Prompt</Label>
              <Input
                id="preset-prompt"
                value={newPrompt}
                onChange={(e) => setNewPrompt(e.target.value)}
                placeholder="Set BPM to 85 and add drums, bass, and keys tracks"
              />
            </div>
            <Button onClick={handleCreate} disabled={saving || !newName.trim() || !newPrompt.trim()} className="w-full">
              {saving ? "Creating..." : "Create Preset"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
