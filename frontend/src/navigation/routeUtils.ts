/**
 * routeUtils — helper thuần (không có side-effect) để thao tác với navigation state.
 * Tách khỏi navigator components để dễ unit test.
 */

/** Kiểu tối thiểu cho navigation state lồng nhau (compatible với react-navigation). */
export type RouteState = {
  index: number;
  routes: Array<{ name: string; state?: RouteState }>;
};

/**
 * Tìm tên route lá đang active bằng cách đệ quy vào nested state.
 * Hàm thuần — không có side-effect, an toàn để test.
 *
 * Ví dụ:
 *  Root { index:0, routes:[{ name:'Main', state:{ index:0, routes:[{
 *    name:'Drawer', state:{ index:1, routes:[{name:'Chat'},{name:'Today'}] }
 *  }] } }] }
 *  → 'Today'
 */
export function getActiveLeafRoute(state: RouteState | undefined): string | undefined {
  if (!state) return undefined;
  const active = state.routes[state.index];
  if (!active) return undefined;
  if (active.state) return getActiveLeafRoute(active.state);
  return active.name;
}
