import { getServerSession } from "next-auth";
import { NextResponse } from "next/server";
import { authOptions } from "@/lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function POST() {
  const session = await getServerSession(authOptions);

  if (!session?.accessToken) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  // Exchange GitHub token with backend for API token
  const res = await fetch(`${API_BASE}/api/auth/github`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      github_token: session.accessToken,
      github_id: session.user.githubId,
      login: session.user.login,
      name: session.user.name,
      email: session.user.email,
      avatar_url: session.user.image,
    }),
  });

  if (!res.ok) {
    return NextResponse.json(
      { error: "Backend auth failed" },
      { status: res.status }
    );
  }

  const data = await res.json();
  return NextResponse.json(data);
}
