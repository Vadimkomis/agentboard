"use client";

import { useSession } from "next-auth/react";
import { redirect } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useBackendToken } from "@/hooks/use-backend-token";
import { useProjects } from "@/hooks/use-projects";
import Link from "next/link";
import type { DashboardStats } from "@/lib/types";

export default function DashboardPage() {
  const { data: session, status } = useSession();
  const { token } = useBackendToken();
  const { data: projects } = useProjects();

  const { data: stats } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: () =>
      api.get<DashboardStats>("/api/dashboard/stats", { token: token! }),
    enabled: !!token,
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

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <StatCard label="Active Projects" value={String(stats?.project_count ?? 0)} />
        <StatCard label="Open Tickets" value={String(stats?.open_ticket_count ?? 0)} />
        <StatCard label="PRs Created" value={String(stats?.pr_count ?? 0)} />
      </div>

      {projects && projects.length > 0 ? (
        <div>
          <h2 className="text-lg font-semibold mb-3">Recent Projects</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.slice(0, 6).map((project) => (
              <Link
                key={project.id}
                href={`/projects/${project.id}/board`}
                className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-5 hover:border-[var(--primary)]/50 transition-colors"
              >
                <h3 className="font-semibold mb-1">{project.name}</h3>
                <p className="text-sm text-[var(--muted-foreground)]">
                  {project.repo_full_name}
                </p>
              </Link>
            ))}
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-8 text-center">
          <p className="text-[var(--muted-foreground)] mb-4">
            No projects yet. Create your first project to get started.
          </p>
          <Link
            href="/projects"
            className="inline-flex px-4 py-2 rounded-lg bg-[var(--primary)] text-white text-sm font-medium hover:opacity-90 transition-opacity"
          >
            Create Project
          </Link>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-6">
      <p className="text-sm text-[var(--muted-foreground)] mb-1">{label}</p>
      <p className="text-3xl font-bold">{value}</p>
    </div>
  );
}
