"use client";

import { useState } from "react";
import useSWR from "swr";
import { useFormatter, useTranslations } from "next-intl";
import { Button, InputSingleSelect, OnyxLoader, Text } from "@opal/components";
import RunTrace, { NativeTrace } from "@/app/app/factory/RunTrace";
import StoredTrajectories from "@/app/app/factory/StoredTrajectories";

interface MassRun {
  id: string;
  status: string;
  stage: string;
  model: string;
  benchmark?: string;
  selected?: string;
  development?: { initial: number; candidate: number; total: number };
  heldout?: { passed: number; total: number };
  training_status?: string;
  training_manifest?: {
    training_rows: number;
    validation_rows: number;
    submission_eligible?: boolean;
  };
  training?: {
    id?: string;
    status: string;
    model?: string;
    fine_tuned_model?: string | null;
    url?: string;
    deployment_status?: string;
    promotion?: string;
  };
  error?: string;
}

type EpisodeName = "baseline" | "v0" | "v1" | "heldout";

interface Benchmark {
  id: string;
  title: string;
  source: string;
  ready: boolean;
  development_questions: number;
  heldout_questions: number;
}

interface Episode {
  name: EpisodeName;
  results?: {
    passed: number;
    total: number;
    task_passed: number;
    task_total: number;
  };
  usage?: { api_calls?: number; elapsed_seconds?: number };
  telemetry?: { status: string; trace_url?: string };
  trace?: NativeTrace;
}

type ReceiptValue =
  | string
  | number
  | boolean
  | null
  | ReceiptValue[]
  | { [key: string]: ReceiptValue };

interface MassDetail {
  run: MassRun;
  events: { at: string; event: string; [key: string]: ReceiptValue }[];
  episodes: Episode[];
  rhi?: {
    proposal?: ReceiptValue;
    comparison?: ReceiptValue;
    selection?: ReceiptValue;
    initial_workflow?: string;
    candidate_workflow?: string;
  };
}

async function fetchMass<T>(url: string): Promise<T> {
  const response = await fetch(url);
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || response.statusText);
  return value;
}

function httpLink(value?: string): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}

function artifactText(value: ReceiptValue | undefined): string {
  return typeof value === "string"
    ? value
    : JSON.stringify(value, null, 2) || "";
}

function hasActiveWork(run: MassRun): boolean {
  if (["running", "training"].includes(run.status)) return true;
  return (
    !!run.training?.id &&
    !["succeeded", "failed", "cancelled", "canceled"].includes(
      run.training.status
    )
  );
}

export default function MassExperiment() {
  const t = useTranslations("aya.mass");
  const format = useFormatter();
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [selectedEpisode, setSelectedEpisode] = useState<EpisodeName | null>(
    null
  );
  const [starting, setStarting] = useState(false);
  const [selectedBenchmark, setSelectedBenchmark] = useState<string | null>(
    null
  );
  const [startError, setStartError] = useState("");
  const {
    data: runs,
    error: listError,
    mutate,
  } = useSWR<MassRun[]>("/api/aya/mass", fetchMass, { refreshInterval: 4000 });
  const { data: catalog, error: catalogError } = useSWR<{
    benchmarks: Benchmark[];
  }>("/api/aya/mass/catalog", fetchMass, { refreshInterval: 5000 });
  const preferredBenchmark =
    catalog?.benchmarks.find((item) => item.id === "public-sql" && item.ready)
      ?.id || "repository-fixture";
  const benchmark = catalog?.benchmarks.find(
    (item) => item.id === (selectedBenchmark || preferredBenchmark)
  );
  const identity = selectedRun || runs?.[0]?.id;
  const { data: detail, error: detailError } = useSWR<MassDetail>(
    identity ? `/api/aya/mass/${identity}` : null,
    fetchMass,
    { refreshInterval: 3000 }
  );
  const current = detail?.run || runs?.find((run) => run.id === identity);
  const running =
    starting ||
    !!runs?.some(hasActiveWork) ||
    !!(current && hasActiveWork(current));
  const episodes = detail?.episodes || [];
  const episode =
    episodes.find((item) => item.name === selectedEpisode) || episodes.at(-1);
  const baseline = episodes.find((item) => item.name === "baseline");
  const initial = episodes.find((item) => item.name === "v0");
  const candidate = episodes.find((item) => item.name === "v1");
  const ceiling =
    baseline?.results &&
    initial?.results &&
    baseline.results.passed === baseline.results.total &&
    initial.results.passed === initial.results.total;
  const failure =
    startError ||
    listError?.message ||
    catalogError?.message ||
    detailError?.message ||
    current?.error;
  const trainingLink = httpLink(current?.training?.url);
  const trainingSkipped =
    current?.training_status === "insufficient_verified_examples";
  const runBenchmarkId = current?.benchmark || "repository-fixture";
  const runBenchmarkTitle =
    catalog?.benchmarks.find((item) => item.id === runBenchmarkId)?.title ||
    runBenchmarkId;

  async function start() {
    if (!benchmark?.ready || running) return;
    setStarting(true);
    setStartError("");
    try {
      const response = await fetch("/api/aya/mass", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-AYA-Request": "1" },
        body: JSON.stringify({ benchmark: benchmark.id }),
      });
      const value: MassRun & { error?: string } = await response.json();
      if (!response.ok) throw new Error(value.error || response.statusText);
      setSelectedRun(value.id);
      setSelectedEpisode(null);
      await mutate();
    } catch (cause) {
      setStartError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setStarting(false);
    }
  }

  return (
    <section className="flex min-w-0 flex-col gap-6" aria-label={t("title")}>
      <div className="flex flex-col gap-3 py-3">
        <Text
          as="h2"
          font={current ? "heading-h2" : "heading-h1"}
          color="text-05"
        >
          {t("title")}
        </Text>
        <div className="max-w-[800px]">
          <Text as="p" font="main-content-muted" color="text-03">
            {t("description")}
          </Text>
        </div>
        <div className="flex flex-wrap items-center gap-3 pt-2">
          <div className="w-full max-w-[420px]">
            <InputSingleSelect
              value={benchmark?.id || ""}
              defaultOption={preferredBenchmark}
              onValueChange={setSelectedBenchmark}
              placeholder={t("benchmarkLabel")}
              options={(catalog?.benchmarks || []).map((item) => ({
                value: item.id,
                title: item.title,
                disabled: !item.ready,
                suffix: item.ready ? undefined : t("preparing"),
                description: t("benchmarkQuestions", {
                  development: item.development_questions,
                  heldout: item.heldout_questions,
                }),
              }))}
            />
          </div>
          <Button
            onClick={start}
            disabled={running || !runs || !benchmark?.ready}
          >
            {t(running ? "running" : "start")}
          </Button>
          <Button
            prominence="tertiary"
            href="https://github.com/Ali-Maq/mass/pull/1"
          >
            {t("source")}
          </Button>
        </div>
        {benchmark && (
          <div className="flex flex-wrap items-center gap-3">
            <Text as="p" font="secondary-body" color="text-03">
              {benchmark.id === "repository-fixture"
                ? t("bounds")
                : t("benchmarkQuestions", {
                    development: benchmark.development_questions,
                    heldout: benchmark.heldout_questions,
                  })}
            </Text>
            {httpLink(benchmark.source) && (
              <Button
                size="sm"
                prominence="tertiary"
                href={httpLink(benchmark.source)}
              >
                {t("benchmarkSource")}
              </Button>
            )}
          </div>
        )}
      </div>

      <details open={!current}>
        <summary className="cursor-pointer">
          <Text font="secondary-action">{t("howItWorks")}</Text>
        </summary>
        <ol className="grid gap-3 pt-3 sm:grid-cols-2 lg:grid-cols-4">
          {(["search", "checks", "traces", "training"] as const).map(
            (step, index) => (
              <li
                key={step}
                className="flex flex-col gap-2 rounded-12 border border-border-01 bg-background-neutral-00 p-4"
              >
                <Text font="secondary-mono" color="text-03">
                  {format.number(index + 1, { minimumIntegerDigits: 2 })}
                </Text>
                <Text font="main-ui-action">{t(`${step}Title`)}</Text>
                <Text as="p" font="secondary-body" color="text-03">
                  {t(`${step}Description`)}
                </Text>
              </li>
            )
          )}
        </ol>
      </details>

      {failure && (
        <div role="alert" className="rounded-12 bg-status-error-01 p-4">
          <Text color="status-error-05">{failure}</Text>
        </div>
      )}
      {!runs && !listError && (
        <div role="status" className="flex items-center gap-3">
          <OnyxLoader size={24} />
          <Text>{t("loading")}</Text>
        </div>
      )}

      <div className="flex min-w-0 flex-col gap-5 rounded-16 border border-border-01 bg-background-neutral-00 p-5 sm:p-6">
        <div
          className="flex flex-wrap items-start justify-between gap-3"
          aria-live="polite"
        >
          <div className="flex flex-col gap-1">
            <Text as="h3" font="heading-h3">
              {t("resultsTitle")}
            </Text>
            <Text font="secondary-body" color="text-03">
              {current
                ? t("runIdentity", { id: current.id, model: current.model })
                : t("empty")}
            </Text>
            {current && (
              <Text font="secondary-body" color="text-03">
                {t("runBenchmark", { name: runBenchmarkTitle })}
              </Text>
            )}
          </div>
          {current && <Text font="main-ui-action">{current.stage}</Text>}
        </div>
        {ceiling && (
          <div className="rounded-12 bg-background-neutral-02 p-4">
            <Text as="p" font="main-ui-body">
              {t("ceiling")}
            </Text>
          </div>
        )}
        {current?.development && (
          <Text as="p" font="main-ui-action">
            {t("selection", {
              initial: current.development.initial,
              candidate: current.development.candidate,
              total: current.development.total,
              selected: current.selected || t("pending"),
            })}
          </Text>
        )}
        {episodes.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-start">
              <caption className="sr-only">{t("resultsTitle")}</caption>
              <thead>
                <tr>
                  {(
                    ["episode", "score", "calls", "time", "evidence"] as const
                  ).map((key) => (
                    <th
                      key={key}
                      scope="col"
                      className="border-b border-border-01 p-3 text-start"
                    >
                      <Text font="secondary-action" color="text-03">
                        {t(key)}
                      </Text>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {episodes.map((item) => (
                  <tr key={item.name}>
                    <th
                      scope="row"
                      className="border-b border-border-01 p-3 text-start"
                    >
                      <Button
                        size="sm"
                        prominence={
                          episode?.name === item.name ? "secondary" : "tertiary"
                        }
                        onClick={() => setSelectedEpisode(item.name)}
                      >
                        {t(`episodes.${item.name}`)}
                      </Button>
                    </th>
                    <td className="border-b border-border-01 p-3">
                      <Text font="main-ui-action">
                        {item.results
                          ? t("checkScore", {
                              passed: item.results.passed,
                              total: item.results.total,
                            })
                          : t("pending")}
                      </Text>
                      {item.results && (
                        <Text as="p" font="secondary-body" color="text-03">
                          {t("taskScore", {
                            passed: item.results.task_passed,
                            total: item.results.task_total,
                          })}
                        </Text>
                      )}
                    </td>
                    <td className="border-b border-border-01 p-3">
                      <Text>
                        {item.usage?.api_calls === undefined
                          ? t("pending")
                          : format.number(item.usage.api_calls)}
                      </Text>
                    </td>
                    <td className="border-b border-border-01 p-3">
                      <Text>
                        {item.usage?.elapsed_seconds === undefined
                          ? t("pending")
                          : t("seconds", {
                              value: format.number(item.usage.elapsed_seconds, {
                                maximumFractionDigits: 1,
                              }),
                            })}
                      </Text>
                    </td>
                    <td className="border-b border-border-01 p-3">
                      {httpLink(item.telemetry?.trace_url) ? (
                        <Button
                          size="sm"
                          prominence="tertiary"
                          href={httpLink(item.telemetry?.trace_url)}
                        >
                          {t("openTrace")}
                        </Button>
                      ) : (
                        <Text font="secondary-body" color="text-03">
                          {item.telemetry?.status || t("pending")}
                        </Text>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Text color="text-03">{t("waiting")}</Text>
        )}
        <Text as="p" font="secondary-body" color="text-03">
          {t(
            runBenchmarkId === "repository-fixture"
              ? "scoreNote"
              : "publicScoreNote"
          )}
        </Text>
        {episode && (
          <div className="flex min-w-0 flex-col gap-2">
            <Text font="main-ui-action">
              {t("activityFor", { episode: t(`episodes.${episode.name}`) })}
            </Text>
            <RunTrace
              key={`${identity}-${episode.name}`}
              trace={episode.trace}
              running={current?.status === "running" && !episode.results}
            />
          </div>
        )}
        {detail?.rhi && (
          <details className="min-w-0 border-t border-border-01 pt-4">
            <summary className="cursor-pointer">
              <Text font="main-ui-action">{t("strategyTitle")}</Text>
            </summary>
            <div className="flex min-w-0 flex-col gap-4 pt-4">
              <Text as="p" font="secondary-body" color="text-03">
                {t("strategyNote")}
              </Text>
              {(
                [
                  "initial_workflow",
                  "candidate_workflow",
                  "proposal",
                  "comparison",
                  "selection",
                ] as const
              ).map(
                (key) =>
                  Boolean(detail.rhi?.[key]) && (
                    <details key={key}>
                      <summary className="cursor-pointer">
                        <Text font="secondary-action">
                          {t(`strategy.${key}`)}
                        </Text>
                      </summary>
                      <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-12 bg-background-neutral-02 p-4">
                        <Text font="secondary-mono">
                          {artifactText(detail.rhi?.[key])}
                        </Text>
                      </pre>
                    </details>
                  )
              )}
            </div>
          </details>
        )}
      </div>

      <section
        className="flex flex-col gap-3 rounded-16 border border-border-01 bg-background-neutral-00 p-5 sm:p-6"
        aria-label={t("trainingTitle")}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Text as="h3" font="heading-h3">
            {t("trainingTitle")}
          </Text>
          {trainingLink && !trainingSkipped && (
            <Button size="sm" prominence="secondary" href={trainingLink}>
              {t("openTraining")}
            </Button>
          )}
        </div>
        <Text as="p" font="main-ui-action">
          {trainingSkipped
            ? t("trainingSkipped")
            : t("trainingStatus", {
                status:
                  current?.training?.status ||
                  current?.training_status ||
                  t("pending"),
              })}
        </Text>
        {current?.training_manifest && (
          <Text as="p" font="main-ui-body">
            {t("verifiedTrainingCounts", {
              training: current.training_manifest.training_rows,
              validation: current.training_manifest.validation_rows,
            })}
          </Text>
        )}
        <Text as="p" font="secondary-body" color="text-03">
          {t(trainingSkipped ? "trainingThreshold" : "trainingBoundary")}
        </Text>
        {ceiling && candidate?.results && !trainingSkipped && (
          <Text as="p" font="secondary-body" color="text-03">
            {t("trainingSmoke")}
          </Text>
        )}
        {current?.training?.model && (
          <Text font="secondary-mono" wordWrap="wrap-anywhere">
            {current.training.model}
          </Text>
        )}
        {current?.training?.fine_tuned_model && (
          <Text font="secondary-mono" wordWrap="wrap-anywhere">
            {t("trainedModel", { model: current.training.fine_tuned_model })}
          </Text>
        )}
        {current?.training?.deployment_status && (
          <Text as="p" font="secondary-body">
            {t("deploymentStatus", {
              status: current.training.deployment_status,
            })}
          </Text>
        )}
      </section>

      <StoredTrajectories />
      {!!detail?.events.length && (
        <details className="min-w-0">
          <summary className="cursor-pointer">
            <Text font="secondary-action">{t("journal")}</Text>
          </summary>
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words pt-3">
            <Text font="secondary-mono">
              {JSON.stringify(detail.events, null, 2)}
            </Text>
          </pre>
        </details>
      )}
      {!!runs && runs.length > 1 && (
        <details>
          <summary className="cursor-pointer">
            <Text font="secondary-action">{t("history")}</Text>
          </summary>
          <div className="flex flex-wrap gap-2 pt-3">
            {runs.map((run) => (
              <Button
                key={run.id}
                size="sm"
                prominence="tertiary"
                onClick={() => {
                  setSelectedRun(run.id);
                  setSelectedEpisode(null);
                }}
              >
                {t("historyItem", { id: run.id, status: run.status })}
              </Button>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}
