"use client";

import useSWR from "swr";
import { useFormatter, useTranslations } from "next-intl";
import { Button, OnyxLoader, Text } from "@opal/components";

interface StoredCandidate {
  experiment_id: string;
  run_id: string;
  episode: string;
  trace_url?: string;
  passed: number;
  total: number;
  mass_winning_teacher_eligible: boolean;
  usage: {
    api_calls: number;
    total_tokens: number;
    elapsed_seconds: number;
    scope: string;
    price_usd: null;
  };
}

interface TrajectorySelection {
  created_at: string;
  mode: string;
  heldout_rows: number;
  criterion: string;
  cost_scope: string;
  limitations: string;
  candidates: StoredCandidate[];
  selected_counts: { [runId: string]: number };
  selected_rows: number;
}

interface PreparingSelection {
  status: "preparing";
}

type SelectionResponse = TrajectorySelection | PreparingSelection;

async function fetchSelection(url: string): Promise<SelectionResponse> {
  const response = await fetch(url);
  const value: SelectionResponse & { error?: string } = await response.json();
  if (!response.ok) throw new Error(value.error || response.statusText);
  return value;
}

function traceLink(value?: string): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}

export default function StoredTrajectories() {
  const t = useTranslations("aya.mass.trajectories");
  const format = useFormatter();
  const { data: response, error } = useSWR<SelectionResponse>(
    "/api/aya/mass/trajectories",
    fetchSelection,
    { refreshInterval: 10000 }
  );
  const data = response && "candidates" in response ? response : undefined;
  const selected =
    data?.candidates.filter(
      (candidate) => (data.selected_counts[candidate.run_id] || 0) > 0
    ) || [];

  return (
    <section
      className="flex min-w-0 flex-col gap-3 rounded-16 border border-border-01 bg-background-neutral-00 p-5 sm:p-6"
      aria-label={t("title")}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Text as="h3" font="heading-h3">
          {t("title")}
        </Text>
        {data && (
          <Text font="main-ui-action">
            {t("selected", {
              count: data.selected_rows,
              heldout: data.heldout_rows,
            })}
          </Text>
        )}
      </div>
      <Text as="p" font="secondary-body" color="text-03">
        {t("rule")}
      </Text>
      <Text as="p" font="secondary-body" color="text-03">
        {t("preview")}
      </Text>
      {!data && !error && (
        <div aria-live="polite" className="flex items-center gap-2">
          <OnyxLoader size={20} />
          <Text font="secondary-body">{t("loading")}</Text>
        </div>
      )}
      {error && (
        <Text as="p" color="status-error-05">
          {error.message}
        </Text>
      )}
      {selected.map((candidate) => (
        <div
          key={candidate.run_id}
          className="flex flex-wrap items-center justify-between gap-3 border-t border-border-01 pt-3"
        >
          <div className="flex min-w-0 flex-col gap-1">
            <Text font="main-ui-action">
              {t("candidate", {
                episode: candidate.episode,
                count: data?.selected_counts[candidate.run_id] || 0,
              })}
            </Text>
            <Text
              font="secondary-mono"
              color="text-03"
              wordWrap="wrap-anywhere"
            >
              {candidate.run_id}
            </Text>
            <Text font="secondary-body" color="text-03">
              {t("usage", {
                passed: candidate.passed,
                total: candidate.total,
                calls: candidate.usage.api_calls,
                tokens: format.number(candidate.usage.total_tokens),
                seconds: format.number(candidate.usage.elapsed_seconds, {
                  maximumFractionDigits: 1,
                }),
              })}
            </Text>
          </div>
          {traceLink(candidate.trace_url) && (
            <Button
              size="sm"
              prominence="tertiary"
              href={traceLink(candidate.trace_url)}
            >
              {t("trace")}
            </Button>
          )}
        </div>
      ))}
      {data && data.selected_rows === 0 && (
        <Text color="text-03">{t("empty")}</Text>
      )}
      {selected.length > 0 &&
        !selected.some(
          (candidate) => candidate.mass_winning_teacher_eligible
        ) && (
          <Text as="p" font="secondary-body" color="text-03">
            {t("noWinner")}
          </Text>
        )}
      {data && (
        <details>
          <summary className="cursor-pointer">
            <Text font="secondary-action">{t("details")}</Text>
          </summary>
          <div className="flex flex-col gap-2 pt-3">
            <Text as="p" font="secondary-body">
              {data.criterion}
            </Text>
            <Text as="p" font="secondary-body">
              {data.cost_scope}
            </Text>
            <Text as="p" font="secondary-body">
              {data.limitations}
            </Text>
          </div>
        </details>
      )}
    </section>
  );
}
