import { render, screen } from "@tests/setup/test-utils";
import RunTrace, { NativeTrace } from "@/app/app/factory/RunTrace";

const activeTrace: NativeTrace = {
  sessions: [
    {
      id: "worker",
      parent_session_id: null,
      model: "test-model",
      api_call_count: 0,
    },
  ],
  entries: [
    {
      id: "tool-1",
      session: "worker",
      at: 0,
      kind: "tool_call",
      name: "terminal",
      content: "Inspect the task input",
      truncated: false,
    },
  ],
};

describe("native trace usage", () => {
  test("waits for persisted usage instead of presenting zero calls while active", () => {
    const { rerender } = render(<RunTrace trace={activeTrace} running />);
    expect(
      screen.getByText(
        "Model usage pending · 0 child agents · 1 observable events"
      )
    ).toBeInTheDocument();
    expect(screen.queryByText(/^0 model calls/)).not.toBeInTheDocument();

    const completedTrace = {
      ...activeTrace,
      sessions: [{ ...activeTrace.sessions[0]!, api_call_count: 8 }],
    };
    rerender(<RunTrace trace={completedTrace} running={false} />);
    expect(
      screen.getByText("8 model calls · 0 child agents · 1 observable events")
    ).toBeInTheDocument();
    expect(screen.queryByText(/Model usage pending/)).not.toBeInTheDocument();
  });

  test("keeps reported active counts and measured completed zero exact", () => {
    const reportedTrace = {
      ...activeTrace,
      sessions: [{ ...activeTrace.sessions[0]!, api_call_count: 2 }],
    };
    const { rerender } = render(<RunTrace trace={reportedTrace} running />);
    expect(
      screen.getByText("2 model calls · 0 child agents · 1 observable events")
    ).toBeInTheDocument();

    rerender(<RunTrace trace={activeTrace} running={false} />);
    expect(
      screen.getByText("0 model calls · 0 child agents · 1 observable events")
    ).toBeInTheDocument();
  });
});
