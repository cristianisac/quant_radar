import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

/**
 * Manual-refresh epoch.
 *
 * Card lists poll on a fixed 5s interval so the agent's new cards
 * appear without user action. But the **underlying time-series data**
 * stays cached (24h TTL on the backend) — pressing "Refresh data"
 * bumps the epoch, which adds ``refresh=true`` to every ``/api/data``
 * query for one fetch cycle, forcing a real fresh pull from the
 * upstream API.
 */
interface RefreshCtx {
  epoch: number;
  bump: () => void;
}

const Ctx = createContext<RefreshCtx>({ epoch: 0, bump: () => undefined });

export function RefreshProvider({ children }: { children: ReactNode }) {
  const [epoch, setEpoch] = useState(0);
  const bump = useCallback(() => setEpoch((n) => n + 1), []);
  const value = useMemo(() => ({ epoch, bump }), [epoch, bump]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useRefreshEpoch = () => useContext(Ctx);
