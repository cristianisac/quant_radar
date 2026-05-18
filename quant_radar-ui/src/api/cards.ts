import { useQuery } from "@tanstack/react-query";

import { apiDelete, apiGet, apiPost } from "./client";
import type { Card, Target } from "../lib/types";

// Card lists poll every 5 s so new agent-created cards appear without
// user action. The refresh button (Sidebar) layers an explicit
// refresh=true on top for the data fetches.
const POLL_MS = 5_000;

export function useCards(target: Target) {
  return useQuery({
    queryKey: ["cards", target],
    queryFn: () => apiGet<Card[]>(`/api/cards/${target}`),
    refetchInterval: POLL_MS,
  });
}

export function useWorkingState() {
  return useQuery({
    queryKey: ["working-state"],
    queryFn: () => apiGet<{ is_open: boolean }>("/api/working/state"),
    refetchInterval: POLL_MS,
  });
}

export function saveCardToMain(id: string): Promise<{ ok: boolean }> {
  return apiPost(`/api/cards/${id}/save-to-main`);
}

export function deleteCard(id: string, target: Target): Promise<{ ok: boolean }> {
  return apiDelete(`/api/cards/${id}?target=${target}`);
}

export function clearDashboard(target: Target): Promise<{ removed: number }> {
  return apiPost(`/api/cards/clear?target=${target}`);
}
