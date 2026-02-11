"use client";

import { useSession } from "next-auth/react";
import { useEffect, useState } from "react";

export function useBackendToken() {
  const { data: session, status } = useSession();
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (status !== "authenticated") {
      setLoading(status === "loading");
      return;
    }

    const cached = sessionStorage.getItem("backend_token");
    if (cached) {
      setToken(cached);
      setLoading(false);
      return;
    }

    fetch("/api/backend-token", { method: "POST" })
      .then((res) => res.json())
      .then((data) => {
        if (data.access_token) {
          sessionStorage.setItem("backend_token", data.access_token);
          setToken(data.access_token);
        }
      })
      .finally(() => setLoading(false));
  }, [status]);

  return { token, loading };
}
