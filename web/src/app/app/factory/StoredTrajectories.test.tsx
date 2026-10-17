import { render, screen } from "@tests/setup/test-utils";
import StoredTrajectories from "@/app/app/factory/StoredTrajectories";

describe("stored trajectory evidence", () => {
  test("keeps the preparation response visible without inventing a selection", () => {
    // GET /api/aya/mass/trajectories returns this while the report is absent.
    render(<StoredTrajectories />, {
      swrConfig: {
        fallback: { "/api/aya/mass/trajectories": { status: "preparing" } },
        revalidateOnMount: false,
        refreshInterval: 0,
      },
    });
    expect(screen.getByText("Loading stored evidence…")).toBeInTheDocument();
    expect(screen.queryByText(/selected answers ·/)).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  test("shows the recorded selection and trace without claiming a winning teacher", () => {
    // Focused ready-response fixture for GET /api/aya/mass/trajectories.
    render(<StoredTrajectories />, {
      swrConfig: {
        fallback: {
          "/api/aya/mass/trajectories": {
            status: "ready",
            selected_rows: 12,
            heldout_rows: 0,
            selected_counts: { "example-baseline": 12 },
            candidates: [
              {
                experiment_id: "example",
                run_id: "example-baseline",
                episode: "baseline",
                passed: 36,
                total: 36,
                trace_url: "http://localhost:3001/trace/example",
                mass_winning_teacher_eligible: false,
                usage: {
                  api_calls: 1,
                  total_tokens: 2177,
                  elapsed_seconds: 9.14,
                },
              },
            ],
            criterion: "Independent quality first",
            cost_scope: "Whole episode",
            limitations: "No accuracy gain established",
          },
        },
        revalidateOnMount: false,
        refreshInterval: 0,
      },
    });
    expect(
      screen.getByText("12 selected answers · 0 held-out rows")
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open source trace" })
    ).toHaveAttribute("href", "http://localhost:3001/trace/example");
    expect(
      screen.getByText(/No selected trajectory is a winning MASS teacher/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Job submissions and provider status appear under Crusoe training/
      )
    ).toBeInTheDocument();
  });
});
