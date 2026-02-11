"use client";

import { useSession } from "next-auth/react";
import { redirect } from "next/navigation";
import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useBackendToken } from "@/hooks/use-backend-token";
import { toast } from "sonner";

export default function SettingsPage() {
  const { data: session, status } = useSession();
  const { token } = useBackendToken();
  const qc = useQueryClient();
  const [anthropicKey, setAnthropicKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");

  const { data: keyStatus } = useQuery({
    queryKey: ["keys-status"],
    queryFn: () =>
      api.get<{ anthropic_key_set: boolean; openai_key_set: boolean }>(
        "/api/users/me/keys/status",
        { token: token! }
      ),
    enabled: !!token,
  });

  const saveKeys = useMutation({
    mutationFn: (data: { anthropic_key?: string; openai_key?: string }) =>
      api.patch("/api/users/me/keys", data, { token: token! }),
    onSuccess: () => {
      toast.success("API keys saved");
      setAnthropicKey("");
      setOpenaiKey("");
      qc.invalidateQueries({ queryKey: ["keys-status"] });
    },
    onError: () => toast.error("Failed to save keys"),
  });

  if (status === "loading") {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-[var(--primary)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!session) {
    redirect("/auth/signin");
  }

  const handleSave = () => {
    const data: { anthropic_key?: string; openai_key?: string } = {};
    if (anthropicKey) data.anthropic_key = anthropicKey;
    if (openaiKey) data.openai_key = openaiKey;
    if (Object.keys(data).length === 0) {
      toast.error("Enter at least one API key");
      return;
    }
    saveKeys.mutate(data);
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Settings</h1>

      <div className="space-y-6 max-w-2xl">
        <section className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-6">
          <h2 className="text-lg font-semibold mb-4">Profile</h2>
          <div className="flex items-center gap-4">
            {session.user.image && (
              <img src={session.user.image} alt="" className="w-16 h-16 rounded-full" />
            )}
            <div>
              <p className="font-medium">{session.user.name}</p>
              <p className="text-sm text-[var(--muted-foreground)]">@{session.user.login}</p>
              <p className="text-sm text-[var(--muted-foreground)]">{session.user.email}</p>
            </div>
          </div>
        </section>

        <section className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-6">
          <h2 className="text-lg font-semibold mb-4">API Keys</h2>
          <p className="text-sm text-[var(--muted-foreground)] mb-4">
            Provide your own API keys for AI agents. Keys are encrypted at rest.
          </p>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-[var(--muted-foreground)] mb-1">
                Anthropic API Key
                {keyStatus?.anthropic_key_set && (
                  <span className="ml-2 text-xs text-[var(--success)]">Configured</span>
                )}
              </label>
              <input
                type="password"
                value={anthropicKey}
                onChange={(e) => setAnthropicKey(e.target.value)}
                placeholder={
                  keyStatus?.anthropic_key_set ? "********** (update to change)" : "sk-ant-..."
                }
                className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--background)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
              />
            </div>
            <div>
              <label className="block text-sm text-[var(--muted-foreground)] mb-1">
                OpenAI API Key
                {keyStatus?.openai_key_set && (
                  <span className="ml-2 text-xs text-[var(--success)]">Configured</span>
                )}
              </label>
              <input
                type="password"
                value={openaiKey}
                onChange={(e) => setOpenaiKey(e.target.value)}
                placeholder={
                  keyStatus?.openai_key_set ? "********** (update to change)" : "sk-..."
                }
                className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--background)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
              />
            </div>
            <button
              onClick={handleSave}
              disabled={saveKeys.isPending}
              className="px-4 py-2 rounded-lg bg-[var(--primary)] text-white text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {saveKeys.isPending ? "Saving..." : "Save Keys"}
            </button>
          </div>
        </section>
        <BillingSection token={token} />
      </div>
    </div>
  );
}

function BillingSection({ token }: { token: string | null }) {
  const { data: usage } = useQuery({
    queryKey: ["billing-usage"],
    queryFn: () =>
      api.get<{
        plan_tier: string;
        execution_quota: number;
        executions_used: number;
        remaining: number;
      }>("/api/billing/usage", { token: token! }),
    enabled: !!token,
  });

  const { data: plans } = useQuery({
    queryKey: ["billing-plans"],
    queryFn: () =>
      api.get<
        {
          id: string;
          name: string;
          execution_quota: number;
          price_monthly: number;
          features: string[];
        }[]
      >("/api/billing/plans", { token: token! }),
    enabled: !!token,
  });

  const upgrade = useMutation({
    mutationFn: (planId: string) =>
      api.post<{ checkout_url: string }>(
        "/api/billing/checkout",
        { plan_id: planId },
        { token: token! }
      ),
    onSuccess: (data) => {
      window.location.href = data.checkout_url;
    },
    onError: () => toast.error("Failed to start checkout"),
  });

  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-6">
      <h2 className="text-lg font-semibold mb-4">Billing & Usage</h2>

      {usage && (
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm font-medium capitalize">
              {usage.plan_tier} Plan
            </span>
          </div>
          <div className="w-full bg-[var(--secondary)] rounded-full h-2 mb-2">
            <div
              className="bg-[var(--primary)] h-2 rounded-full transition-all"
              style={{
                width: `${Math.min(
                  100,
                  (usage.executions_used / usage.execution_quota) * 100
                )}%`,
              }}
            />
          </div>
          <p className="text-xs text-[var(--muted-foreground)]">
            {usage.executions_used} / {usage.execution_quota} executions used
            ({usage.remaining} remaining)
          </p>
        </div>
      )}

      {plans && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {plans.map((plan) => (
            <div
              key={plan.id}
              className={`rounded-lg border p-4 ${
                usage?.plan_tier === plan.id
                  ? "border-[var(--primary)] bg-[var(--primary)]/5"
                  : "border-[var(--border)]"
              }`}
            >
              <h3 className="font-semibold">{plan.name}</h3>
              <p className="text-2xl font-bold mt-1">
                ${plan.price_monthly}
                <span className="text-sm font-normal text-[var(--muted-foreground)]">
                  /mo
                </span>
              </p>
              <ul className="mt-3 space-y-1">
                {plan.features.map((f, i) => (
                  <li
                    key={i}
                    className="text-xs text-[var(--muted-foreground)] flex items-center gap-1"
                  >
                    <span className="text-[var(--success)]">&#10003;</span> {f}
                  </li>
                ))}
              </ul>
              {usage?.plan_tier === plan.id ? (
                <p className="mt-3 text-xs text-[var(--primary)] font-medium">
                  Current plan
                </p>
              ) : plan.price_monthly > 0 ? (
                <button
                  onClick={() => upgrade.mutate(plan.id)}
                  disabled={upgrade.isPending}
                  className="mt-3 w-full px-3 py-1.5 rounded-lg bg-[var(--primary)] text-white text-xs font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {upgrade.isPending ? "..." : "Upgrade"}
                </button>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
