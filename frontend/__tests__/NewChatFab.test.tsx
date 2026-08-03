/**
 * Test NewChatFab + logic hiển thị route (getActiveLeafRoute) + GlobalFab.
 *
 * Chiến lược:
 *  1. Test hàm thuần getActiveLeafRoute — không cần navigation mock.
 *  2. Test NewChatFab component — render + onPress.
 *  3. Test GlobalFab component — mock useNavigationState + navigationRef.dispatch.
 *
 * Lưu ý RNTL v14: render() là async, phải await.
 */
import React from "react";
import { render, fireEvent } from "@testing-library/react-native";
import { NewChatFab } from "../src/ui/NewChatFab";
import { GlobalFab } from "../src/navigation/GlobalFab";
import { getActiveLeafRoute, type RouteState } from "../src/navigation/routeUtils";

// ─── Mocks ───────────────────────────────────────────────────────────────────

jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 44, bottom: 34, left: 0, right: 0 }),
  SafeAreaProvider: ({ children }: { children: React.ReactNode }) => children,
}));

jest.mock("@expo/vector-icons", () => ({
  Ionicons: () => null,
}));

// Mock useNavigationState để kiểm soát route đang active trong GlobalFab tests.
// CommonActions.navigate mock trả về argument như identity để kiểm tra dễ hơn.
jest.mock("@react-navigation/native", () => ({
  useNavigationState: jest.fn(),
  CommonActions: {
    navigate: jest.fn((payload: unknown) => payload),
  },
}));

// Mock navigationRef — chỉ cần dispatch là jest.fn() để verify được call.
jest.mock("../src/navigation/navigationRef", () => ({
  navigationRef: { dispatch: jest.fn() },
}));

// Import mocked versions (sau jest.mock để lấy đúng mock instance)
import { useNavigationState, CommonActions } from "@react-navigation/native";
import { navigationRef } from "../src/navigation/navigationRef";

// Tắt tiếng React warnings trong test
const originalError = console.error;
beforeAll(() => {
  console.error = (...args: unknown[]) => {
    if (typeof args[0] === "string" && args[0].includes("Warning:")) return;
    originalError(...args);
  };
});
afterAll(() => {
  console.error = originalError;
});

// ─── getActiveLeafRoute — hàm thuần ─────────────────────────────────────────

describe("getActiveLeafRoute", () => {
  it("trả về undefined khi state undefined", () => {
    expect(getActiveLeafRoute(undefined)).toBeUndefined();
  });

  it("trả về tên route khi không có nested state", () => {
    const state: RouteState = {
      index: 0,
      routes: [{ name: "Today" }],
    };
    expect(getActiveLeafRoute(state)).toBe("Today");
  });

  it("đệ quy vào nested state và trả về leaf khi đang ở Chat", () => {
    // Root → Main → Drawer → Chat (index 0)
    const state: RouteState = {
      index: 0,
      routes: [
        {
          name: "Main",
          state: {
            index: 0,
            routes: [
              {
                name: "Drawer",
                state: {
                  index: 0,
                  routes: [{ name: "Chat" }, { name: "Today" }],
                },
              },
            ],
          },
        },
      ],
    };
    expect(getActiveLeafRoute(state)).toBe("Chat");
  });

  it("đệ quy vào nested state và trả về Today khi drawer ở Today", () => {
    // Root → Main → Drawer → Today (index 1)
    const state: RouteState = {
      index: 0,
      routes: [
        {
          name: "Main",
          state: {
            index: 0,
            routes: [
              {
                name: "Drawer",
                state: {
                  index: 1,
                  routes: [{ name: "Chat" }, { name: "Today" }],
                },
              },
            ],
          },
        },
      ],
    };
    expect(getActiveLeafRoute(state)).toBe("Today");
  });

  it("trả về tên màn push khi push screen đang active trên Main Stack", () => {
    // Root → Main → Team (push screen, index 1 trên Main Stack)
    const state: RouteState = {
      index: 0,
      routes: [
        {
          name: "Main",
          state: {
            index: 1,
            routes: [
              {
                name: "Drawer",
                state: {
                  index: 0,
                  routes: [{ name: "Chat" }],
                },
              },
              { name: "Team" },
            ],
          },
        },
      ],
    };
    expect(getActiveLeafRoute(state)).toBe("Team");
  });

  it("chọn đúng route theo index khi có nhiều routes", () => {
    const state: RouteState = {
      index: 2,
      routes: [{ name: "A" }, { name: "B" }, { name: "C" }],
    };
    expect(getActiveLeafRoute(state)).toBe("C");
  });
});

// ─── NewChatFab component ────────────────────────────────────────────────────

describe("NewChatFab", () => {
  it("render với accessibilityLabel đúng", async () => {
    const { getByLabelText } = await render(<NewChatFab onPress={() => {}} />);
    expect(getByLabelText("Cuộc trò chuyện mới")).toBeTruthy();
  });

  it("gọi onPress khi bấm FAB", async () => {
    const onPress = jest.fn();
    const { getByLabelText } = await render(<NewChatFab onPress={onPress} />);
    fireEvent.press(getByLabelText("Cuộc trò chuyện mới"));
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it("có accessibilityRole button", async () => {
    const { getByRole } = await render(<NewChatFab onPress={() => {}} />);
    expect(getByRole("button", { name: "Cuộc trò chuyện mới" })).toBeTruthy();
  });
});

// ─── GlobalFab component ─────────────────────────────────────────────────────

describe("GlobalFab", () => {
  const mockedUseNav = useNavigationState as jest.Mock;
  const mockedCommonActionsNavigate = CommonActions.navigate as jest.Mock;
  const mockedDispatch = navigationRef.dispatch as jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("trả về null (không render FAB) khi active route là Chat", async () => {
    // useNavigationState sẽ trả về kết quả selector — mock trả thẳng "Chat"
    mockedUseNav.mockReturnValue("Chat");
    const { queryByLabelText } = await render(<GlobalFab />);
    expect(queryByLabelText("Cuộc trò chuyện mới")).toBeNull();
  });

  it("render FAB khi active route là Today", async () => {
    mockedUseNav.mockReturnValue("Today");
    const { getByLabelText } = await render(<GlobalFab />);
    expect(getByLabelText("Cuộc trò chuyện mới")).toBeTruthy();
  });

  it("onPress gọi navigationRef.dispatch với CommonActions.navigate({ name: 'Chat' })", async () => {
    mockedUseNav.mockReturnValue("Today");
    const { getByLabelText } = await render(<GlobalFab />);
    fireEvent.press(getByLabelText("Cuộc trò chuyện mới"));
    // Kiểm tra CommonActions.navigate được gọi với đúng tham số
    expect(mockedCommonActionsNavigate).toHaveBeenCalledWith({ name: "Chat", params: {} });
    // Kiểm tra dispatch được gọi với kết quả của CommonActions.navigate
    expect(mockedDispatch).toHaveBeenCalledTimes(1);
    expect(mockedDispatch).toHaveBeenCalledWith(
      mockedCommonActionsNavigate.mock.results[0].value,
    );
  });
});
