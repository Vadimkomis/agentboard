"use client";

import { useSession, signOut } from "next-auth/react";
import { NotificationBell } from "./notification-bell";

export function Header() {
  const { data: session } = useSession();

  return (
    <header className="h-14 border-b border-[var(--border)] bg-[var(--card)] flex items-center justify-between px-6">
      <div />
      <div className="flex items-center gap-4">
        {session?.user && (
          <>
            <NotificationBell />
            <span className="text-sm text-[var(--muted-foreground)]">
              {session.user.login}
            </span>
            {session.user.image && (
              <img
                src={session.user.image}
                alt=""
                className="w-8 h-8 rounded-full"
              />
            )}
            <button
              onClick={() => signOut()}
              className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
            >
              Sign out
            </button>
          </>
        )}
      </div>
    </header>
  );
}
