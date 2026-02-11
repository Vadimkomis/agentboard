"use client";

import { cn } from "@/lib/utils";

const agentConfig: Record<string, { color: string; label: string }> = {
  backend: { color: "bg-blue-500/20 text-blue-400 border-blue-500/30", label: "Backend" },
  frontend: { color: "bg-purple-500/20 text-purple-400 border-purple-500/30", label: "Frontend" },
  mobile: { color: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30", label: "Mobile" },
  devops: { color: "bg-orange-500/20 text-orange-400 border-orange-500/30", label: "DevOps" },
  qa: { color: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30", label: "QA" },
  fullstack: { color: "bg-indigo-500/20 text-indigo-400 border-indigo-500/30", label: "Fullstack" },
  docs: { color: "bg-gray-500/20 text-gray-400 border-gray-500/30", label: "Docs" },
  pm: { color: "bg-pink-500/20 text-pink-400 border-pink-500/30", label: "PM" },
};

export function AgentStatusBadge({ agentType }: { agentType: string }) {
  const config = agentConfig[agentType] || agentConfig.fullstack;
  return (
    <span
      className={cn(
        "inline-flex items-center text-xs px-2 py-0.5 rounded-full border",
        config.color
      )}
    >
      {config.label}
    </span>
  );
}
