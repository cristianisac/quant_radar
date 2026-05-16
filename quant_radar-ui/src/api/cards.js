import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";
export function useCards(target, refreshMs) {
    return useQuery({
        queryKey: ["cards", target],
        queryFn: () => apiGet(`/api/cards/${target}`),
        refetchInterval: refreshMs,
    });
}
export function useWorkingState(refreshMs) {
    return useQuery({
        queryKey: ["working-state"],
        queryFn: () => apiGet("/api/working/state"),
        refetchInterval: refreshMs,
    });
}
