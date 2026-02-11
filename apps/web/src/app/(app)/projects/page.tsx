"use client";

import { useSession } from "next-auth/react";
import { redirect } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import Link from "next/link";
import { useProjects, useCreateProject, useDeleteProject } from "@/hooks/use-projects";

export default function ProjectsPage() {
  const { data: session, status } = useSession();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const { data: projects, isLoading } = useProjects();

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
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Projects</h1>
        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 rounded-lg bg-[var(--primary)] text-white text-sm font-medium hover:opacity-90 transition-opacity"
        >
          New Project
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-32">
          <div className="w-6 h-6 border-2 border-[var(--primary)] border-t-transparent rounded-full animate-spin" />
        </div>
      ) : projects && projects.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-8 text-center">
          <p className="text-[var(--muted-foreground)]">
            No projects yet. Link a GitHub repository to create your first project.
          </p>
        </div>
      )}

      {showCreateModal && (
        <CreateProjectModal onClose={() => setShowCreateModal(false)} />
      )}
    </div>
  );
}

function ProjectCard({
  project,
}: {
  project: { id: string; name: string; repo_full_name: string; created_at: string };
}) {
  const deleteProject = useDeleteProject();
  const [confirming, setConfirming] = useState(false);

  const handleDelete = async () => {
    try {
      await deleteProject.mutateAsync(project.id);
      toast.success("Project deleted");
    } catch {
      toast.error("Failed to delete project");
    }
  };

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-5 group">
      <Link href={`/projects/${project.id}/board`} className="block mb-3">
        <h3 className="font-semibold hover:text-[var(--primary)] transition-colors">
          {project.name}
        </h3>
        <p className="text-sm text-[var(--muted-foreground)] mt-1">
          {project.repo_full_name}
        </p>
        <p className="text-xs text-[var(--muted-foreground)] mt-2">
          Created {new Date(project.created_at).toLocaleDateString()}
        </p>
      </Link>
      <div className="flex gap-2">
        <Link
          href={`/projects/${project.id}/board`}
          className="text-xs px-3 py-1.5 rounded-lg bg-[var(--primary)] text-white hover:opacity-90 transition-opacity"
        >
          Open Board
        </Link>
        {confirming ? (
          <button
            onClick={handleDelete}
            className="text-xs px-3 py-1.5 rounded-lg bg-[var(--destructive)] text-white hover:opacity-90 transition-opacity"
          >
            Confirm Delete
          </button>
        ) : (
          <button
            onClick={() => setConfirming(true)}
            className="text-xs px-3 py-1.5 rounded-lg text-[var(--muted-foreground)] hover:text-[var(--destructive)] transition-colors"
          >
            Delete
          </button>
        )}
      </div>
    </div>
  );
}

function CreateProjectModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const createProject = useCreateProject();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Extract repo_full_name from URL
    const match = repoUrl.match(/github\.com\/([^/]+\/[^/]+)/);
    if (!match) {
      toast.error("Invalid GitHub URL. Expected format: https://github.com/owner/repo");
      return;
    }
    const repoFullName = match[1].replace(/\.git$/, "");

    try {
      await createProject.mutateAsync({
        name,
        repo_full_name: repoFullName,
        repo_url: repoUrl,
      });
      toast.success("Project created");
      onClose();
    } catch {
      toast.error("Failed to create project");
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="w-full max-w-md rounded-xl border border-[var(--border)] bg-[var(--card)] p-6">
        <h2 className="text-lg font-bold mb-4">New Project</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-[var(--muted-foreground)] mb-1">
              Project Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My Awesome Project"
              className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
              required
            />
          </div>
          <div>
            <label className="block text-sm text-[var(--muted-foreground)] mb-1">
              GitHub Repository URL
            </label>
            <input
              type="url"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="https://github.com/owner/repo"
              className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
              required
            />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createProject.isPending}
              className="px-4 py-2 rounded-lg bg-[var(--primary)] text-white text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {createProject.isPending ? "Creating..." : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
