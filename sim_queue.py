"""
Shared asyncio queues that act as the message bus between actors.

Flow:
  user_sim  ──placed_orders──▶  store_sim
  store_sim ──ready_orders───▶  robot_sim
  store/robot/user ──terminal_orders──▶ main

Each item in placed_orders_queue is a tuple:
  {
    "order_db_id": int,
    "order_ref": str,
    "order_total": float,
  }

  order_db_id  — the integer primary key returned by the backend (used for PATCH)
  order_ref    — the "#123456" string used for the free-order endpoint
  order_total  — normal order value; Stripe mode charges this amount

Each item in ready_orders_queue is:
  {
    "order_db_id": int,
    "order_ref": str,
    "order_total": float,
  }

Each item in terminal_orders_queue is:
  {"order_db_id": int | None, "order_ref": str | None, "status": str}
"""

import asyncio

placed_orders_queue: asyncio.Queue = asyncio.Queue()
ready_orders_queue: asyncio.Queue = asyncio.Queue()
terminal_orders_queue: asyncio.Queue = asyncio.Queue()
