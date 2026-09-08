import { Routes, Route, Navigate } from "react-router-dom";
import type { RouteObject } from "react-router-dom";
import AppLayout from "./layout/AppLayout";
import Dashboard from "./pages/Dashboard";
import Tenants from "./pages/Tenants";
import RoomStatus from "./pages/RoomStatus";
import Reception from "./pages/Reception";
import ReceptionWorkbench from "./pages/ReceptionWorkbench";
import Guests from "./pages/Guests";
import Analytics from "./pages/Analytics";
import Bookings from "./pages/Bookings";
import Billing from "./pages/Billing";
import NotFound from "./pages/NotFound";
import NightAudit from "./pages/NightAudit";
import Approvals from "./pages/Approvals";
import Housekeeping from "./pages/Housekeeping";
import Notifications from "./pages/Notifications";
import Alerts from "./pages/Alerts";
import Group from "./pages/Group";
import Members from "./pages/Members";
import Commission from "./pages/Commission";
import Shifts from "./pages/Shifts";
import WakeUp from "./pages/WakeUp";
import PSB from "./pages/PSB";
import Users from "./pages/Users";
import Audit from "./pages/Audit";
import Reconciliation from "./pages/Reconciliation";
import Rates from "./pages/Rates";
import RateCalendar from "./pages/RateCalendar";
import MpOrders from "./pages/MpOrders";
import AIChat from "./pages/AIChat";
import OpenApi from "./pages/OpenApi";
import Yield from "./pages/Yield";
import Login from "./pages/Login";
import RoomTypes from "./pages/RoomTypes";
import Rooms from "./pages/Rooms";
import Adjustments from "./pages/Adjustments";
import PricePolicy from "./pages/PricePolicy";
import Channel from "./pages/Channel";
import ChannelCenter from "./pages/ChannelCenter";
import Reports from "./pages/Reports";
import GroupBlock from "./pages/GroupBlock";
import Pos from "./pages/Pos";
import Kds from "./pages/Kds";
import Complaints from "./pages/Complaints";
import ArAccounts from "./pages/ArAccounts";
import Deposits from "./pages/Deposits";
import CheckInRegister from "./pages/CheckInRegister";

/**
 * 布局内路由表（供 AppLayout 选项卡 keep-alive 渲染复用）。
 * 注意顺序：index 重定向放最前，通配 NotFound 放最后。
 */
export const layoutRoutes: RouteObject[] = [
  { path: "/", element: <Navigate to="/dashboard" replace /> },
  { path: "dashboard", element: <Dashboard /> },
  { path: "bookings", element: <Bookings /> },
  { path: "billing", element: <Billing /> },
  { path: "nightaudit", element: <NightAudit /> },
  { path: "approvals", element: <Approvals /> },
  { path: "housekeeping", element: <Housekeeping /> },
  { path: "notifications", element: <Notifications /> },
  { path: "alerts", element: <Alerts /> },
  { path: "group", element: <Group /> },
  { path: "members", element: <Members /> },
  { path: "commission", element: <Commission /> },
  { path: "shifts", element: <Shifts /> },
  { path: "wakeup", element: <WakeUp /> },
  { path: "psb", element: <PSB /> },
  { path: "users", element: <Users /> },
  { path: "audit", element: <Audit /> },
  { path: "reconciliation", element: <Reconciliation /> },
  { path: "rates", element: <Rates /> },
  { path: "rate-calendar", element: <RateCalendar /> },
  { path: "mp-orders", element: <MpOrders /> },
  { path: "ai-chat", element: <AIChat /> },
  { path: "openapi", element: <OpenApi /> },
  { path: "yield", element: <Yield /> },
  { path: "room-types", element: <RoomTypes /> },
  { path: "rooms-inventory", element: <Rooms /> },
  { path: "adjustments", element: <Adjustments /> },
  { path: "price-policy", element: <PricePolicy /> },
  { path: "channel-push", element: <Channel /> },
  { path: "reports", element: <Reports /> },
  { path: "tenants", element: <Tenants /> },
  { path: "group-blocks", element: <GroupBlock /> },
  { path: "pos", element: <Pos /> },
  { path: "kds", element: <Kds /> },
  { path: "complaints", element: <Complaints /> },
  { path: "ar-accounts", element: <ArAccounts /> },
  { path: "deposits", element: <Deposits /> },
          { path: "channel-center", element: <ChannelCenter /> },
          { path: "deposits", element: <Deposits /> },
  { path: "rooms", element: <RoomStatus /> },
  { path: "reception", element: <Reception /> },
  { path: "reception-workbench", element: <ReceptionWorkbench /> },
  { path: "check-in-register", element: <CheckInRegister /> },
  { path: "guests", element: <Guests /> },
  { path: "analytics", element: <Analytics /> },
  { path: "*", element: <NotFound /> },
];

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/*" element={<AppLayout />} />
    </Routes>
  );
}
