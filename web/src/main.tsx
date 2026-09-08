import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ConfigProvider, App as AntApp } from "antd";
import zhCN from "antd/locale/zh_CN";
import "antd/dist/reset.css";
import "./styles/global.css";
import App from "./App";
import { TenantProvider } from "./store/tenant";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: "#1677ff",
          borderRadius: 10,
          colorBgLayout: "#f5f7fa",
          colorText: "#1f2329",
          colorTextSecondary: "#646a73",
          colorBorderSecondary: "#eef0f4",
          fontSize: 14,
          boxShadowTertiary: "0 2px 8px rgba(31,35,41,.06)",
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif",
        },
        components: {
          Layout: { headerBg: "#ffffff", headerHeight: 56, bodyBg: "#f5f6fa" },
          Card: { paddingLG: 20, borderRadiusLG: 12 },
          Table: {
            headerBg: "#fafbfd",
            headerColor: "#646a73",
            rowHoverBg: "#f7faff",
            headerSplitColor: "transparent",
            cellPaddingBlock: 11,
            cellPaddingInline: 12,
            cellPaddingBlockSM: 8,
            cellPaddingInlineSM: 10,
          },
          Menu: { itemBorderRadius: 6, itemMarginInline: 8 },
          Modal: { borderRadiusLG: 12 },
          Button: { fontWeight: 500 },
        },
      }}
    >
      <AntApp>
        <BrowserRouter>
          <TenantProvider>
            <App />
          </TenantProvider>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>
);
