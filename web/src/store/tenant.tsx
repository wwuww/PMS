import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { listTenants, listHotels } from "../api/endpoints";
import type { Tenant, Hotel } from "../api/types";

interface TenantCtx {
  tenants: Tenant[];
  tenantCode: string;
  hotelId: string | null;
  hotels: Hotel[];
  loading: boolean;
  setTenant: (code: string) => Promise<void>;
  setHotel: (id: string) => void;
  refresh: () => Promise<void>;
}

const Ctx = createContext<TenantCtx | null>(null);

const LS_TENANT = "pms.tenantCode";
const LS_HOTEL = "pms.hotelId";

export function TenantProvider({ children }: { children: ReactNode }) {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantCode, setTenantCode] = useState<string>(
    localStorage.getItem(LS_TENANT) || "DEMO2026"
  );
  const [hotels, setHotels] = useState<Hotel[]>([]);
  const [hotelId, setHotelId] = useState<string | null>(() => {
    return localStorage.getItem(LS_HOTEL);
  });
  const [loading, setLoading] = useState(true);

  async function loadHotels(code: string) {
    try {
      const hs = await listHotels(code);
      setHotels(hs);
      const saved = localStorage.getItem(LS_HOTEL);
      if (saved && hs.some((h) => h.id === saved)) {
        setHotelId(saved);
      } else if (hs.length > 0) {
        setHotelId(hs[0].id);
        localStorage.setItem(LS_HOTEL, String(hs[0].id));
      } else {
        setHotelId(null);
      }
    } catch {
      setHotels([]);
      setHotelId(null);
    }
  }

  const refresh = async () => {
    setLoading(true);
    const ts = await listTenants();
    setTenants(ts);
    if (!ts.some((t) => t.code === tenantCode) && ts.length) {
      setTenantCode(ts[0].code);
    }
    await loadHotels(tenantCode);
    setLoading(false);
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setTenant = async (code: string) => {
    setTenantCode(code);
    localStorage.setItem(LS_TENANT, code);
    await loadHotels(code);
  };

  const setHotel = (id: string) => {
    setHotelId(id);
    localStorage.setItem(LS_HOTEL, String(id));
  };

  return (
    <Ctx.Provider
      value={{
        tenants,
        tenantCode,
        hotelId,
        hotels,
        loading,
        setTenant,
        setHotel,
        refresh,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useTenant(): TenantCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useTenant must be used within TenantProvider");
  return v;
}
