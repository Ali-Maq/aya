"use client";

import { useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import RunTrace, { NativeTrace } from "@/app/app/factory/RunTrace";
import MassExperiment from "@/app/app/factory/MassExperiment";
import useSWR from "swr";
import MinimalMarkdown from "@/components/chat/MinimalMarkdown";
import { useTranslations, useFormatter } from "next-intl";
import {
  Button,
  Text,
  InputTypeIn,
  InputTextArea,
  Tabs,
} from "@opal/components";
import { SvgBranch, SvgArrowRight, SvgCheckCircle } from "@opal/icons";

interface Profile {
  id: string;
  repository: string;
  title: string;
  feature: string;
  reference: string;
}
interface FeatureRequest {
  number: number;
  title: string;
  url: string;
  repository: string;
  ready: boolean;
}
interface Queue {
  fetched_at: string;
  requests: FeatureRequest[];
  profiles: Profile[];
}
interface Run {
  id: string;
  status: string;
  issue_number: number;
  target_repository?: string;
  profile?: string;
  started_at: string;
  error?: string;
  pr_url?: string;
  commit?: string;
  passed?: number;
  total?: number;
  stage?: string;
}
interface RunEvent {
  at: string;
  event: string;
  [key: string]: unknown;
}
interface Detail {
  run: Run;
  events: RunEvent[];
  snapshot: unknown;
  evidence?: unknown;
  source?: string;
  report?: { attempts: { passed: number; total: number }[] };
  audits: unknown[];
  trace?: NativeTrace;
  live_checks?: unknown;
  checks?: { html_url: string; name: string; conclusion: string }[];
}
interface Answer {
  answer: string;
  sql: string;
  columns: string[];
  rows: unknown[][];
  fetched_at: string;
  sources: string[];
  model: string;
  trace: unknown[];
  commit: string;
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  const value: T & { error?: string } = await response.json();
  if (!response.ok) throw new Error(value.error || response.statusText);
  return value;
}
type FactoryCommand =
  | { repository: string; feature: string; reference: string }
  | { number: number; repository: string }
  | { question: string };

async function post<T>(path: string, body: FactoryCommand): Promise<T> {
  const response = await fetch(`/api/aya/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-AYA-Request": "1" },
    body: JSON.stringify(body),
  });
  const value: T & { error?: string } = await response.json();
  if (!response.ok) throw new Error(value.error || response.statusText);
  return value;
}

export default function FactoryPage() {
  const t = useTranslations("aya");
  const format = useFormatter();
  const router = useRouter();
  const searchParams = useSearchParams();
  const workflow =
    searchParams.get("tab") === "improve" ? "improve" : "recover";

  function selectWorkflow(value: string) {
    const params = new URLSearchParams(searchParams);
    params.set("tab", value === "improve" ? "improve" : "recover");
    router.replace(`/app/factory?${params.toString()}`, { scroll: false });
  }
  const {
    data: queue,
    error: queueError,
    mutate: refreshQueue,
  } = useSWR<Queue>("/api/aya/requests", fetchJson);
  const { data: runs, mutate: refreshRuns } = useSWR<Run[]>(
    "/api/aya/runs",
    fetchJson,
    { refreshInterval: 4000 }
  );
  const { data: deployed } = useSWR<{ pr_url: string; commit: string } | null>(
    "/api/aya/deployment",
    fetchJson,
    { refreshInterval: 4000 }
  );
  const progress = useRef<HTMLElement>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState<{
    repository: string;
    feature: string;
    reference: string;
  } | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const profile = queue?.profiles[0];
  const form = draft || {
    repository: profile?.repository || "",
    feature: profile?.feature || "",
    reference: profile?.reference || "",
  };
  const active = selected || runs?.[0]?.id;
  const { data: detail, error: detailError } = useSWR<Detail>(
    active ? `/api/aya/runs/${active}` : null,
    fetchJson,
    { refreshInterval: 3000 }
  );
  const busy = submitting || runs?.some((run) => run.status === "running");
  const events = new Set(detail?.events.map((event) => event.event));
  const steps = [
    { key: "stepRequest", done: events.has("request_frozen") },
    {
      key: "stepInvestigate",
      done:
        events.has("reference_investigated") ||
        events.has("binary_investigated"),
    },
    { key: "stepBuild", done: events.has("acceptance_passed") },
    { key: "stepVerify", done: events.has("target_tests_passed") },
    { key: "stepDeliver", done: events.has("ci_passed") },
  ] as const;

  async function createRequest() {
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      const result = await post<{ ready: boolean }>("requests", form);
      setNotice(t(result.ready ? "createdReady" : "createdProposal"));
      await refreshQueue();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSubmitting(false);
    }
  }
  async function start(request: FeatureRequest) {
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      const value = await post<Run>("run", {
        number: request.number,
        repository: request.repository,
      });
      setSelected(value.id);
      progress.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      await refreshRuns();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSubmitting(false);
    }
  }
  async function ask() {
    setAsking(true);
    setError("");
    setAnswer(null);
    try {
      setAnswer(
        await post<Answer>("ask", {
          question: question || t("exampleQuestion"),
        })
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setAsking(false);
    }
  }
  return (
    <div className="h-full min-w-0 overflow-x-hidden overflow-y-auto bg-background-neutral-01">
      <div className="mx-auto flex w-full min-w-0 max-w-[1240px] flex-col gap-6 p-6">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border-01 pb-4">
          <div className="flex items-center gap-3">
            <SvgBranch className="size-7 text-text-05" />
            <Text as="h1" font="heading-h2">
              {t("title")}
            </Text>
            <Text color="text-03">{t("subtitle")}</Text>
          </div>
          <Button prominence="tertiary" href="https://github.com/Ali-Maq/aya">
            {t("repository")}
          </Button>
        </header>
        <Text as="h2" font="heading-h2">
          {t("workflows.heading")}
        </Text>
        <Tabs value={workflow} onValueChange={selectWorkflow} gap={6}>
          <Tabs.List>
            <Tabs.Trigger
              value="recover"
              description={t("workflows.reverseDescription")}
            >
              {t("workflows.reverseTitle")}
            </Tabs.Trigger>
            <Tabs.Trigger
              value="improve"
              description={t("workflows.improveDescription")}
            >
              {t("workflows.improveTitle")}
            </Tabs.Trigger>
          </Tabs.List>
          <Tabs.Content value="improve" keepMounted>
            <MassExperiment />
          </Tabs.Content>
          <Tabs.Content value="recover" keepMounted>
            <div className="flex min-w-0 flex-col gap-6">
              <div className="flex flex-col gap-2">
                <Text as="h2" font="heading-h2">
                  {t("newHeadline")}
                </Text>
                <Text as="p" color="text-03">
                  {t("newDescription")}
                </Text>
              </div>
              {(error || queueError || detailError) && (
                <div role="alert" className="rounded-12 bg-status-error-01 p-4">
                  <Text color="status-error-05">
                    {error || queueError?.message || detailError?.message}
                  </Text>
                </div>
              )}
              {notice && (
                <div
                  role="status"
                  className="rounded-12 border border-border-01 p-4"
                >
                  <Text>{notice}</Text>
                </div>
              )}
              <div className="grid min-w-0 gap-5 md:grid-cols-2">
                <section className="flex min-w-0 flex-col gap-4 rounded-16 border border-border-01 bg-background-neutral-00 p-6">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Text as="h3" font="heading-h3">
                      {t("newRequest")}
                    </Text>
                    <Button
                      size="sm"
                      prominence="tertiary"
                      onClick={() =>
                        profile &&
                        setDraft({
                          repository: profile.repository,
                          feature: profile.feature,
                          reference: profile.reference,
                        })
                      }
                    >
                      {t("useExample")}
                    </Button>
                  </div>
                  <label htmlFor="aya-repo">
                    <Text font="main-ui-action">{t("targetLabel")}</Text>
                  </label>
                  <InputTypeIn
                    id="aya-repo"
                    value={form.repository}
                    onChange={(event) =>
                      setDraft({ ...form, repository: event.target.value })
                    }
                    placeholder="owner/repository"
                  />
                  <label htmlFor="aya-feature">
                    <Text font="main-ui-action">{t("featureLabel")}</Text>
                  </label>
                  <InputTextArea
                    id="aya-feature"
                    rows={4}
                    maxLength={4000}
                    value={form.feature}
                    onChange={(event) =>
                      setDraft({ ...form, feature: event.target.value })
                    }
                  />
                  <label htmlFor="aya-reference">
                    <Text font="main-ui-action">{t("referenceLabel")}</Text>
                  </label>
                  <InputTypeIn
                    id="aya-reference"
                    type="url"
                    value={form.reference}
                    onChange={(event) =>
                      setDraft({ ...form, reference: event.target.value })
                    }
                  />
                  <Text font="secondary-body" color="text-03">
                    {t("contractNote")}
                  </Text>
                  <div>
                    <Button
                      icon={SvgArrowRight}
                      disabled={submitting || !profile}
                      onClick={createRequest}
                    >
                      {submitting ? t("saving") : t("createRequest")}
                    </Button>
                  </div>
                </section>
                <section className="flex min-w-0 flex-col gap-4 rounded-16 border border-border-01 bg-background-neutral-00 p-6">
                  <div className="flex items-center justify-between">
                    <Text as="h3" font="heading-h3">
                      {t("requests")}
                    </Text>
                    <Button
                      size="sm"
                      prominence="tertiary"
                      onClick={() => refreshQueue()}
                    >
                      {t("refresh")}
                    </Button>
                  </div>
                  {!queue && <Text color="text-03">{t("loading")}</Text>}
                  {queue?.requests.length === 0 && (
                    <Text color="text-03">{t("startHint")}</Text>
                  )}
                  <div className="flex max-h-[440px] flex-col gap-3 overflow-y-auto">
                    {queue?.requests.map((request) => (
                      <article
                        key={`${request.repository}-${request.number}`}
                        className="flex flex-col gap-3 rounded-12 border border-border-01 p-4"
                      >
                        <Text
                          font="secondary-body"
                          color="text-03"
                          wordWrap="wrap-anywhere"
                        >{`${request.repository} #${request.number}`}</Text>
                        <Text as="h3" font="main-ui-action">
                          {request.title}
                        </Text>
                        <div className="flex flex-wrap gap-2">
                          <Button
                            size="sm"
                            disabled={busy || !request.ready}
                            onClick={() => start(request)}
                          >
                            {request.ready
                              ? t("buildFeature")
                              : t("needsReview")}
                          </Button>
                          <Button
                            size="sm"
                            prominence="tertiary"
                            href={request.url}
                          >
                            {t("issue")}
                          </Button>
                        </div>
                      </article>
                    ))}
                  </div>
                  {queue && (
                    <Text font="secondary-body" color="text-03">
                      {t("fetched", {
                        time: format.dateTime(new Date(queue.fetched_at), {
                          hour: "numeric",
                          minute: "numeric",
                          second: "numeric",
                        }),
                      })}
                    </Text>
                  )}
                  <div className="mt-auto border-t border-border-01 pt-4">
                    <Text as="p" font="secondary-action">
                      {t("engine")}
                    </Text>
                    <Text as="p" font="secondary-body" color="text-03">
                      {t("newStack")}
                    </Text>
                  </div>
                </section>
              </div>
              <section
                ref={progress}
                className="flex min-w-0 flex-col gap-5 rounded-16 border border-border-01 bg-background-neutral-00 p-6"
                aria-live="polite"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <Text as="h3" font="heading-h3">
                    {t("progress")}
                  </Text>
                  {detail?.run.pr_url && (
                    <Button href={detail.run.pr_url}>{t("pullRequest")}</Button>
                  )}
                </div>
                {detail && (
                  <Text
                    font="secondary-body"
                    color="text-03"
                  >{`${detail.run.target_repository || "Ali-Maq/aya-data-recipes"} #${detail.run.issue_number}`}</Text>
                )}
                <ol className="grid gap-3 sm:grid-cols-5">
                  {steps.map((step, index) => (
                    <li
                      key={step.key}
                      className="flex items-center gap-2 rounded-12 bg-background-neutral-02 p-3"
                    >
                      {step.done ? (
                        <SvgCheckCircle className="size-5 shrink-0" />
                      ) : (
                        <Text color="text-03">{String(index + 1)}</Text>
                      )}
                      <Text font="secondary-action">{t(step.key)}</Text>
                    </li>
                  ))}
                </ol>
                {detail ? (
                  <div className="flex flex-wrap items-center gap-5">
                    <Text font="main-ui-action">
                      {detail.run.stage || detail.run.status}
                    </Text>
                    {detail.run.total && (
                      <Text>
                        {t("checksCount", {
                          passed: detail.run.passed || 0,
                          total: detail.run.total,
                        })}
                      </Text>
                    )}
                    {detail.checks
                      ?.filter(
                        (check) =>
                          check.conclusion === "success" &&
                          ["aya-sql", "contract", "aya-usage"].includes(
                            check.name
                          )
                      )
                      .slice(0, 1)
                      .map((check) => (
                        <Button
                          key={check.html_url}
                          size="sm"
                          prominence="tertiary"
                          href={check.html_url}
                        >
                          {t("ciPassed")}
                        </Button>
                      ))}
                    {detail.run.status === "complete" &&
                      detail.run.profile === "saved-json-export" && (
                        <Button
                          size="sm"
                          prominence="tertiary"
                          href="http://localhost:3032"
                        >
                          {t("openProduct")}
                        </Button>
                      )}
                    {detail.run.error && (
                      <Text color="status-error-05">{detail.run.error}</Text>
                    )}
                  </div>
                ) : (
                  <Text color="text-03">{t("startHint")}</Text>
                )}
                <div className="flex flex-wrap gap-4">
                  {detail?.report?.attempts.map((attempt, index) => (
                    <Text
                      key={index}
                      font="secondary-body"
                      color={
                        attempt.passed === attempt.total
                          ? "text-03"
                          : "status-error-05"
                      }
                    >
                      {t("attemptResult", {
                        attempt: index + 1,
                        passed: attempt.passed,
                        total: attempt.total,
                        status: t(
                          attempt.passed === attempt.total
                            ? "checksPassed"
                            : "checksRejected"
                        ),
                      })}
                    </Text>
                  ))}
                </div>
                <details>
                  <summary className="cursor-pointer">
                    <Text font="secondary-action">{t("testingTitle")}</Text>
                  </summary>
                  <ol className="flex list-decimal flex-col gap-2 ps-5 pt-3">
                    {(
                      [
                        "testContract",
                        "testOracle",
                        "testHoldout",
                        "testDelivery",
                      ] as const
                    ).map((key) => (
                      <li key={key}>
                        <Text font="secondary-body">{t(key)}</Text>
                      </li>
                    ))}
                  </ol>
                </details>
                <RunTrace
                  trace={detail?.trace}
                  running={detail?.run.status === "running"}
                />
                <details>
                  <summary className="cursor-pointer">
                    <Text font="secondary-action">{t("history")}</Text>
                  </summary>
                  <div className="flex flex-wrap gap-2 pt-3">
                    {runs?.slice(0, 12).map((run) => (
                      <Button
                        key={run.id}
                        size="sm"
                        prominence={
                          active === run.id ? "secondary" : "tertiary"
                        }
                        onClick={() => setSelected(run.id)}
                      >{`${run.target_repository || run.profile || t("jsonDemo")} · ${format.dateTime(new Date(run.started_at), { hour: "numeric", minute: "numeric" })} · ${run.status}`}</Button>
                    ))}
                  </div>
                </details>
              </section>
              {(!detail ||
                detail.run.profile === "crusoe-repository-analyst") && (
                <section className="flex min-w-0 flex-col gap-4 rounded-16 border border-border-01 bg-background-neutral-00 p-6">
                  <div>
                    <Text as="h3" font="heading-h3">
                      {t("tryFeature")}
                    </Text>
                    <Text as="p" color="text-03">
                      {deployed ? t("tryDescription") : t("tryPending")}
                    </Text>
                  </div>
                  <div className="flex flex-col gap-3 sm:flex-row">
                    <div className="min-w-0 flex-1">
                      <InputTypeIn
                        aria-label={t("questionLabel")}
                        value={question}
                        onChange={(event) => setQuestion(event.target.value)}
                        placeholder={t("exampleQuestion")}
                        maxLength={1000}
                      />
                    </div>
                    <Button disabled={!deployed || asking} onClick={ask}>
                      {asking ? t("asking") : t("askCrusoe")}
                    </Button>
                  </div>
                  {answer && (
                    <div className="flex min-w-0 flex-col gap-4">
                      <details>
                        <summary className="cursor-pointer">
                          <Text font="secondary-action">
                            {t("modelExplanation")}
                          </Text>
                        </summary>
                        <MinimalMarkdown content={answer.answer} />
                      </details>
                      <div className="overflow-x-auto">
                        <table className="w-full text-left">
                          <thead>
                            <tr>
                              {answer.columns.map((column, index) => (
                                <th
                                  key={`${column}-${index}`}
                                  className="border-b border-border-01 p-3"
                                >
                                  <Text font="secondary-action">{column}</Text>
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {answer.rows.map((row, index) => (
                              <tr key={index}>
                                {row.map((cell, column) => (
                                  <td
                                    key={column}
                                    className="border-b border-border-01 p-3"
                                  >
                                    <Text font="secondary-body">
                                      {cell === null ? "null" : String(cell)}
                                    </Text>
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <pre className="overflow-x-auto rounded-12 bg-background-neutral-02 p-4">
                        <Text font="secondary-mono">{answer.sql}</Text>
                      </pre>
                      <Text font="secondary-body" color="text-03">
                        {t("liveProof", {
                          model: answer.model,
                          count: answer.sources.length,
                          commit: answer.commit.slice(0, 8),
                        })}
                      </Text>
                      <details>
                        <summary className="cursor-pointer">
                          <Text>{t("queryEvidence")}</Text>
                        </summary>
                        <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words p-3">
                          <Text font="secondary-mono">
                            {JSON.stringify(
                              {
                                fetched_at: answer.fetched_at,
                                sources: answer.sources,
                                trace: answer.trace,
                              },
                              null,
                              2
                            )}
                          </Text>
                        </pre>
                      </details>
                    </div>
                  )}
                </section>
              )}
              {detail && (
                <details className="min-w-0 rounded-16 border border-border-01 p-5">
                  <summary className="cursor-pointer">
                    <Text font="secondary-action">
                      {t("technicalEvidence")}
                    </Text>
                  </summary>
                  <div className="flex flex-col gap-4 pt-4">
                    <Text font="secondary-body" color="text-03">
                      {t("boundary")}
                    </Text>
                    {(
                      [
                        "events",
                        "snapshot",
                        "evidence",
                        "source",
                        "report",
                        "audits",
                        "live_checks",
                      ] as const
                    ).map((key) => (
                      <details key={key}>
                        <summary className="cursor-pointer">
                          <Text font="secondary-action">
                            {t(`detail_${key}`)}
                          </Text>
                        </summary>
                        <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-12 bg-background-neutral-02 p-4">
                          <Text font="secondary-mono">
                            {typeof detail[key] === "string"
                              ? detail[key]
                              : JSON.stringify(detail[key], null, 2)}
                          </Text>
                        </pre>
                      </details>
                    ))}
                  </div>
                </details>
              )}
            </div>
          </Tabs.Content>
        </Tabs>
      </div>
    </div>
  );
}
