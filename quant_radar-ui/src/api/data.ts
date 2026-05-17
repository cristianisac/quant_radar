import { useQuery } from "@tanstack/react-query";

import { apiGet } from "./client";
import type { DataRef, TimeSeriesResponse } from "../lib/types";
import { useRefreshEpoch } from "../lib/refresh";

export function useDataRef(ref: DataRef | null) {
  const { epoch } = useRefreshEpoch();
  return useQuery({
    enabled: ref !== null,
    queryKey: ["data", ref, epoch],
    queryFn: () => {
      if (!ref) throw new Error("ref is null");
      const params = new URLSearchParams({
        source: ref.source,
        kind: ref.kind,
        name: ref.name,
        interval: ref.interval ?? "1d",
      });
      if (ref.start) params.set("start", ref.start);
      if (ref.end) params.set("end", ref.end);
      // Bumping the epoch (Refresh button) adds refresh=true so the
      // server bypasses its TTL cache and pulls fresh from the upstream.
      if (epoch > 0) params.set("refresh", "true");
      return apiGet<TimeSeriesResponse>(`/api/data?${params}`);
    },
    staleTime: 5 * 60 * 1000,
  });
}
