"use client";

import type { ReactNode } from "react";
import { OrdersProvider } from "../contexts/OrdersContext";

export function AppShell({ children }: { children: ReactNode }) {
  return <OrdersProvider>{children}</OrdersProvider>;
}
