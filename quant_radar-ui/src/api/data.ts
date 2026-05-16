import { useQuery } from "@tanstack/react-query";

import { apiGet } from "./client";
import type { DataRef, TimeSeriesResponse } from "../lib/types";

export function useDataRef(ref: DataRef | null) {
  return useQuery({
    enabled: ref !== null,
    queryKey: ["data", ref],
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
      return apiGet<TimeSeriesResponse>(`/api/data?${params}`);
    },
    staleTime: 5 * 60 * 1000, // cache OHLCV on the client for 5 min
  });
}
