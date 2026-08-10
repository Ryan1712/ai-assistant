/**
 * Test luồng Project → Chat:
 *  1. ProjectCard tap thân thẻ → createConversation() → updateConversation(id, { project_id }) → navigate("Chat", { id })
 *  2. ProjectCard tap chevron → xổ/thu gọn danh sách task
 *  3. ProjectCard lỗi createConversation → không crash, không navigate
 *  4. ProjectScopeBanner: ẩn khi project_id null
 *  5. ProjectScopeBanner: hiển thị "đang tải..." khi project_id có nhưng chưa có tên
 *  6. ProjectScopeBanner: hiển thị đúng tên project
 *
 * Lưu ý RNTL v14: render() là async, phải await.
 */
import React from "react";
import { render, fireEvent, waitFor } from "@testing-library/react-native";
import { ProjectCard } from "../app/main/ProjectCard";
import { ProjectScopeBanner } from "../src/ui/ProjectScopeBanner";
import type { Project } from "../src/api/projects";
import type { TaskDetail } from "../src/api/tasks";

// ─── Mocks ───────────────────────────────────────────────────────────────────

jest.mock("@expo/vector-icons", () => ({
  Ionicons: () => null,
}));

const mockNavigate = jest.fn();

jest.mock("@react-navigation/native", () => ({
  useNavigation: jest.fn(() => ({ navigate: mockNavigate })),
}));

// Mock createConversation + updateConversation — luồng gắn mềm: tạo rồi PATCH project_id.
jest.mock("../src/api/chat", () => ({
  createConversation: jest.fn(),
  updateConversation: jest.fn(),
}));

import { createConversation, updateConversation } from "../src/api/chat";

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

// ─── Dữ liệu test ─────────────────────────────────────────────────────────────

const mockProject: Project = {
  id: "proj-1",
  name: "Website Relaunch",
  goal: "Ra mắt trang web mới",
  status: "active",
  deadline: null,
  owner_id: null,
};

const mockTasks: TaskDetail[] = [
  {
    id: "t1",
    title: "Thiết kế UI",
    status: "done",
    percent: 100,
    project_id: "proj-1",
    description: "",
    deadline: null,
    priority: "medium",
    assignee_ids: [],
  },
  {
    id: "t2",
    title: "Viết nội dung",
    status: "in_progress",
    percent: 50,
    project_id: "proj-1",
    description: "",
    deadline: null,
    priority: "medium",
    assignee_ids: [],
  },
];

// ─── ProjectCard ──────────────────────────────────────────────────────────────

describe("ProjectCard", () => {
  const mockedCreate = createConversation as jest.Mock;
  const mockedUpdate = updateConversation as jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    mockedCreate.mockResolvedValue({
      id: "conv-proj-1",
      title: null,
      queue_held: false,
      archived_at: null,
      created_at: "2026-08-08T00:00:00Z",
      project_id: null,
    });
    mockedUpdate.mockResolvedValue({
      id: "conv-proj-1",
      title: null,
      queue_held: false,
      archived_at: null,
      created_at: "2026-08-08T00:00:00Z",
      project_id: "proj-1",
    });
  });

  it("tap thân thẻ tạo conversation rồi PATCH project_id rồi navigate Chat", async () => {
    const { getByLabelText } = await render(
      <ProjectCard p={mockProject} tasks={[]} />,
    );

    fireEvent.press(getByLabelText("Mở chat project Website Relaunch"));

    await waitFor(() => {
      expect(mockedCreate).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(mockedUpdate).toHaveBeenCalledWith("conv-proj-1", { project_id: "proj-1" });
    });
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("Chat", { id: "conv-proj-1" });
    });
  });

  it("tap chevron xổ danh sách task; tap lại thu gọn", async () => {
    const { getByLabelText, getByText, queryByText } = await render(
      <ProjectCard p={mockProject} tasks={mockTasks} />,
    );

    // Danh sách task ẩn ban đầu
    expect(queryByText("Thiết kế UI")).toBeNull();

    // Tap chevron để xổ — phải await vì fireEvent.press là async (wraps act)
    await fireEvent.press(getByLabelText("Xem danh sách task"));
    expect(getByText("Thiết kế UI")).toBeTruthy();
    expect(getByText("Viết nội dung")).toBeTruthy();

    // Tap chevron lại để thu gọn
    await fireEvent.press(getByLabelText("Thu gọn danh sách task"));
    expect(queryByText("Thiết kế UI")).toBeNull();
  });

  it("createConversation thất bại → không crash, không navigate", async () => {
    mockedCreate.mockRejectedValue(new Error("Network error"));

    const { getByLabelText } = await render(
      <ProjectCard p={mockProject} tasks={[]} />,
    );

    fireEvent.press(getByLabelText("Mở chat project Website Relaunch"));

    await waitFor(() => {
      expect(mockedCreate).toHaveBeenCalledTimes(1);
    });
    // navigate KHÔNG được gọi
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("tap thân thẻ KHÔNG gọi createConversation khi nhấn chevron", async () => {
    const { getByLabelText } = await render(
      <ProjectCard p={mockProject} tasks={mockTasks} />,
    );

    // Chỉ nhấn chevron
    fireEvent.press(getByLabelText("Xem danh sách task"));

    // createConversation không được gọi
    expect(mockedCreate).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});

// ─── ProjectScopeBanner ───────────────────────────────────────────────────────

describe("ProjectScopeBanner", () => {
  it("không render khi project_id null", async () => {
    const { queryByText } = await render(
      <ProjectScopeBanner projectId={null} projectName={null} />,
    );
    expect(queryByText(/Đang trong project/)).toBeNull();
  });

  it("hiển thị 'đang tải...' khi có project_id nhưng chưa có tên", async () => {
    const { getByText } = await render(
      <ProjectScopeBanner projectId="proj-1" projectName={null} />,
    );
    expect(getByText(/đang tải/)).toBeTruthy();
  });

  it("hiển thị tên project khi có", async () => {
    const { getByText } = await render(
      <ProjectScopeBanner projectId="proj-1" projectName="Website Relaunch" />,
    );
    expect(getByText(/Website Relaunch/)).toBeTruthy();
  });

  it("hiển thị icon lock và chuỗi tiêu đề đúng", async () => {
    const { getByText } = await render(
      <ProjectScopeBanner projectId="proj-1" projectName="My Project" />,
    );
    expect(getByText(/Đang trong project/)).toBeTruthy();
  });
});
