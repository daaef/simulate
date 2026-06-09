"use client";

import React, { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import {
  ApiRequestError,
  autoLoginForOrders,
  clearOrdersSession,
  fetchFainzyOrdersPage,
  type FainzyOrder,
  type OrdersStoreSession,
} from "../lib/api";

interface OrdersContextType {
  session: OrdersStoreSession | null;
  orders: FainzyOrder[];
  loading: boolean;
  loadingMore: boolean;
  error: string | null;
  sessionError: string | null;
  reload: () => void;
  updateOrder: (id: number, patch: Partial<FainzyOrder>) => void;
}

const OrdersContext = createContext<OrdersContextType>({
  session: null,
  orders: [],
  loading: false,
  loadingMore: false,
  error: null,
  sessionError: null,
  reload: () => {},
  updateOrder: () => {},
});

export function useOrders() {
  return useContext(OrdersContext);
}

export function OrdersProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<OrdersStoreSession | null>(null);
  const [orders, setOrders] = useState<FainzyOrder[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const abortRef = useRef<boolean>(false);

  function formatErr(err: unknown): string {
    if (err instanceof ApiRequestError) return err.message;
    if (err instanceof Error) return err.message;
    return "Something went wrong.";
  }

  const fetchOrders = useCallback(async (sess: OrdersStoreSession) => {
    abortRef.current = false;
    setLoading(true);
    setError(null);
    setOrders([]);

    let nextUrl: string | null | undefined = undefined;
    let firstPage = true;

    try {
      do {
        if (abortRef.current) break;
        const result = await fetchFainzyOrdersPage(nextUrl ?? undefined);
        if (abortRef.current) break;

        if (firstPage) {
          setOrders(result.orders);
          setLoading(false);
          firstPage = false;
        } else {
          setOrders((prev) => [...prev, ...result.orders]);
        }

        nextUrl = result.next;
        if (nextUrl) setLoadingMore(true);
      } while (nextUrl);
    } catch (err) {
      if (!abortRef.current) setError(formatErr(err));
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, []);

  const doLogin = useCallback(async () => {
    setSessionError(null);
    try {
      const s = await autoLoginForOrders();
      setSession(s);
      void fetchOrders(s);
    } catch (err) {
      clearOrdersSession();
      setSession(null);
      setSessionError(formatErr(err));
    }
  }, [fetchOrders]);

  const reload = useCallback(() => {
    abortRef.current = true;
    if (session) {
      void fetchOrders(session);
    } else {
      void doLogin();
    }
  }, [session, fetchOrders, doLogin]);

  const updateOrder = useCallback((id: number, patch: Partial<FainzyOrder>) => {
    setOrders((prev) => prev.map((o) => (o.id === id ? { ...o, ...patch } : o)));
  }, []);

  useEffect(() => {
    void doLogin();
    return () => { abortRef.current = true; };
  }, []);

  return (
    <OrdersContext.Provider value={{ session, orders, loading, loadingMore, error, sessionError, reload, updateOrder }}>
      {children}
    </OrdersContext.Provider>
  );
}
