"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { clearToken, getToken } from "./api";

export function useAuthGuard() {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/login");
    } else {
      setReady(true);
    }
  }, [router]);

  return ready;
}

export function useLogout() {
  const router = useRouter();
  return useCallback(() => {
    clearToken();
    router.replace("/login");
  }, [router]);
}
