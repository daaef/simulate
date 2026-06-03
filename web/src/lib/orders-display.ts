type OrderItemNameSource = {
  menu?: Array<{
    menu?: {
      name?: string | null;
    } | null;
  } | null>;
};

export function getOrderItemNames(order: OrderItemNameSource): string[] {
  return (order.menu ?? [])
    .map((item) => item?.menu?.name?.trim() ?? "")
    .filter((name) => name.length > 0);
}
