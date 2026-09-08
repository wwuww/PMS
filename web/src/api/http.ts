import axios, {
  AxiosError,
  type InternalAxiosRequestConfig,
} from "axios";
import { message } from "antd";

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "/api/v1",
  timeout: 15000,
});

const TOKEN_KEY = "pms_token";
const REFRESH_KEY = "pms_refresh_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function setRefreshToken(token: string | null): void {
  if (token) localStorage.setItem(REFRESH_KEY, token);
  else localStorage.removeItem(REFRESH_KEY);
}

// 请求拦截器：携带登录 token（后端路由已强制会话鉴权，缺失/失效即 401）
http.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers = config.headers ?? {};
    (config.headers as Record<string, string>).Authorization = `Bearer ${token}`;
  }
  return config;
});

http.interceptors.response.use(
  (resp) => resp,
  async (error: AxiosError<{ detail?: string }>) => {
    const status = error.response?.status;
    const config = error.config as
      | (InternalAxiosRequestConfig & { _retried?: boolean })
      | undefined;

    // 401 且持有刷新令牌：先尝试静默刷新并重放原请求（仅一次，防死循环）
    if (
      status === 401 &&
      config &&
      !config._retried &&
      getRefreshToken() &&
      !String(config.url || "").includes("/auth/")
    ) {
      config._retried = true;
      try {
        const tenantCode =
          localStorage.getItem("pms.tenantCode") || "DEMO2026";
        const { data } = await axios.post(
          `${http.defaults.baseURL}/tenants/${tenantCode}/auth/refresh`,
          { refresh_token: getRefreshToken() }
        );
        setToken(data.token);
        setRefreshToken(data.refresh_token);
        // M32.18 T05：刷新成功后同步更新权限集合
        localStorage.setItem("pms_permissions", JSON.stringify(data.permissions ?? []));
        (config.headers as Record<string, string>).Authorization =
          `Bearer ${data.token}`;
        return http.request(config);
      } catch {
        setRefreshToken(null);
        // 刷新失败 → 走下方统一 401 登出逻辑
      }
    }

    // 会话失效：清除本地凭证并跳回登录页（避免重复弹错与死循环）
    if (status === 401) {
      setToken(null);
      setRefreshToken(null);
      localStorage.removeItem("pms_user");
      // M32.18 T05：会话失效时同步清空权限
      localStorage.removeItem("pms_permissions");
      if (location.pathname !== "/login") {
        location.href = "/login";
      }
    } else if (status === 403) {
      // 授权层拦截：登录态有效但权限不足（M8-3 路由级 RBAC）
      message.error(error.response?.data?.detail || "权限不足：当前账号无权执行该操作");
    } else if (status === 429) {
      // 限流拦截（M18-2）
      message.warning(error.response?.data?.detail || "请求过于频繁，请稍后重试");
    }
    const msg =
      error.response?.data?.detail ||
      error.message ||
      "请求失败";
    return Promise.reject(new Error(msg));
  }
);

export function wsBase(): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}`;
}
