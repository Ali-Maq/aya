import { render, screen, within } from "@tests/setup/test-utils";
import MassExperiment from "@/app/app/factory/MassExperiment";

test("completed evaluation explains why training was not submitted", () => {
  const run = {
    id: "public-example",
    status: "completed",
    stage: "Evaluation complete",
    model: "example-model",
    benchmark: "public-sql",
    training_status: "insufficient_verified_examples",
    training_manifest: {
      training_rows: 8,
      validation_rows: 1,
      submission_eligible: false,
    },
  };
  // API-response fixtures cover a finished experiment with no training job.
  render(<MassExperiment />, {
    swrConfig: {
      fallback: {
        "/api/aya/mass": [run],
        "/api/aya/mass/public-example": { run, episodes: [], events: [] },
        "/api/aya/mass/catalog": {
          benchmarks: [
            {
              id: "public-sql",
              title: "Public SQL example",
              ready: true,
              source: "https://example.org/dataset",
              development_questions: 12,
              heldout_questions: 6,
            },
          ],
        },
        "/api/aya/mass/trajectories": { status: "preparing" },
      },
      revalidateOnMount: false,
      refreshInterval: 0,
    },
  });
  const training = within(
    screen.getByRole("region", { name: "Crusoe training" })
  );
  expect(
    training.getByText("Evaluation complete · training not submitted")
  ).toBeInTheDocument();
  expect(
    training.getByText(
      "Verified examples: 8/10 training · 1/2 preassigned validation"
    )
  ).toBeInTheDocument();
  expect(
    training.queryByRole("link", { name: "Open training job" })
  ).not.toBeInTheDocument();
  expect(
    training.queryByText(/Provider status: Pending/)
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Run SQL experiment" })
  ).not.toBeDisabled();
});
