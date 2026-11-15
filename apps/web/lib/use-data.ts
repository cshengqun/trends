"use client";

import { useEffect, useState } from "react";

type Result<T> =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; data: T };

export function useData<T>(path: string | null) {
  const [attempt, setAttempt] = useState(0);
  const [request, setRequest] = useState<{ key: string; result: Result<T> }>();
  const key = path + "#" + attempt;
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch("/api/v1" + path, { signal: controller.signal, cache: "no-store" });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error?.message ?? "数据加载失败");
        if (!controller.signal.aborted) setRequest({ key, result: { status: "success", data: payload.data } });
      } catch (error) {
        if (controller.signal.aborted) return;
        setRequest({ key, result: { status: "error", message: error instanceof Error ? error.message : "数据加载失败" } });
      }
    }
    void load();
    return () => controller.abort();
  }, [key, path]);
  const result: Result<T> = request?.key === key ? request.result : { status: "loading" };
  return { ...result, retry: () => setAttempt((value) => value + 1) };
}
