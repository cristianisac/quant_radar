import { useQuery } from "@tanstack/react-query";

import { apiGet } from "./client";
import type { Card, Target } from "../lib/types";

export function useCards(target: Target, refreshMs: number) {
  return useQuery({
    queryKey: ["cards", target],
    queryFn: () => apiGet<Card[]>(`/api/cards/${target}`),
    refetchInterval: refreshMs,
  });
}

export function useWorkingState(refreshMs: number) {
  return useQuery({
    queryKey: ["working-state"],
    queryFn: () => apiGet<{ is_open: boolean }>("/api/working/state"),
    refetchInterval: refreshMs,
  });
}
