"use client";

import { useState } from "react";
import useSWR from "swr";
import { useTranslations, useFormatter } from "next-intl";
import { Button, Text } from "@opal/components";
import {
  SvgBranch,
  SvgArrowRight,
  SvgTerminal,
  SvgCheckCircle,
} from "@opal/icons";
import { cn } from "@opal/utils";

interface FeatureRequest {
  number: number;
  title: string;
  body: string;
  url: string;
  repository: string;
  updated_at: string;
}
interface Queue {
  fetched_at: string;
  source: string;
  requests: FeatureRequest[];
}
interface Event {
  at: string;
  event: string;
  [key: string]: unknown;
}
interface Run {
  id: string;
  status: string;
  issue_number: number;
  started_at: string;
  error?: string;
  pr_url?: string;
  commit?: string;
  passed?: number;
  total?: number;
  stage?: string;
}
interface Detail {
  run: Run;
  events: Event[];
  snapshot: unknown;
  plan?: unknown;
  evidence?: unknown;
  source?: string;
  report?: unknown;
  audits: unknown[];
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || response.statusText);
  return value;
}

export default function FactoryPage() {
  const t = useTranslations("aya");
  const format = useFormatter();
  const {
    data: queue,
    error: queueError,
    mutate: refreshQueue,
  } = useSWR<Queue>("/api/aya/requests", fetchJson, {
    revalidateOnFocus: true,
  });
  const { data: runs, mutate: refreshRuns } = useSWR<Run[]>(
    "/api/aya/runs",
    fetchJson,
    {
      refreshInterval: 4000,
    }
  );
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<
    "source" | "contract" | "evidence" | "tests" | "agents"
  >("evidence");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const active = selected || runs?.[0]?.id;
  const { data: detail, error: detailError } = useSWR<Detail>(
    active ? `/api/aya/runs/${active}` : null,
    fetchJson,
    { refreshInterval: 3000 }
  );
  const busy = submitting || runs?.some((run) => run.status === "running");

  async function start(number: number) {
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch("/api/aya/run", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-AYA-Request": "1" },
        body: JSON.stringify({ number }),
      });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error || response.statusText);
      setSelected(value.id);
      await refreshRuns();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSubmitting(false);
    }
  }

  const artifact =
    tab === "source"
      ? detail?.source
      : JSON.stringify(
          tab === "contract"
            ? detail?.snapshot
            : tab === "evidence"
              ? detail?.evidence
              : tab === "tests"
                ? detail?.report
                : detail?.audits,
          null,
          2
        );
  return (
    <div className="h-full min-w-0 overflow-x-hidden overflow-y-auto bg-background-neutral-01">
      <div className="mx-auto flex w-full min-w-0 max-w-[1440px] flex-col gap-6 p-6">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border-01 pb-6">
          <div className="flex items-center gap-3">
            <SvgBranch className="size-8 text-text-05" />
            <div>
              <Text as="h1" font="heading-h2">
                {t("title")}
              </Text>
              <Text as="p" font="secondary-body" color="text-03">
                {t("subtitle")}
              </Text>
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              prominence="secondary"
              href="https://github.com/Ali-Maq/aya"
            >
              {t("repository")}
            </Button>
            <Button prominence="secondary" href="http://localhost:3032">
              {t("openProduct")}
            </Button>
          </div>
        </header>
        <div className="flex flex-col gap-2">
          <Text as="h2" font="heading-h2">
            {t("headline")}
          </Text>
          <Text as="p" font="main-content-muted" color="text-03">
            {t("description")}
          </Text>
        </div>
        {(error || queueError || detailError) && (
          <div role="alert" className="rounded-12 bg-status-error-01 p-4">
            <Text color="status-error-05">
              {error || queueError?.message || detailError?.message}
            </Text>
          </div>
        )}
        <div className="grid min-w-0 gap-5 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
          <section className="flex min-w-0 flex-col gap-4 rounded-16 border border-border-01 bg-background-neutral-00 p-6">
            <div className="flex items-center justify-between">
              <Text font="heading-h3">{t("requests")}</Text>
              <Button
                prominence="tertiary"
                size="sm"
                onClick={() => refreshQueue()}
              >
                {t("refresh")}
              </Button>
            </div>
            {!queue && <Text color="text-03">{t("loading")}</Text>}
            {queue?.requests.length === 0 && (
              <Text color="text-03">{t("empty")}</Text>
            )}
            {queue?.requests.map((request) => (
              <div
                key={request.number}
                className="flex flex-col gap-4 rounded-12 border border-border-01 p-5"
              >
                <Text
                  font="secondary-mono"
                  color="text-03"
                >{`${request.repository} #${request.number}`}</Text>
                <Text as="h3" font="heading-h3">
                  {request.title}
                </Text>
                <div className="max-h-36 overflow-y-auto whitespace-pre-wrap break-words">
                  <Text
                    font="secondary-body"
                    color="text-03"
                    wordWrap="wrap-anywhere"
                  >
                    {request.body}
                  </Text>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    icon={SvgArrowRight}
                    disabled={busy}
                    onClick={() => start(request.number)}
                  >
                    {busy ? t("running") : t("build")}
                  </Button>
                  <Button prominence="secondary" href={request.url}>
                    {t("issue")}
                  </Button>
                </div>
              </div>
            ))}
            {queue && (
              <Text font="secondary-mono" color="text-03">
                {t("fetched", {
                  time: format.dateTime(new Date(queue.fetched_at), {
                    hour: "numeric",
                    minute: "numeric",
                    second: "numeric",
                  }),
                })}
              </Text>
            )}
            <div className="border-t border-border-01 pt-4">
              <Text font="secondary-action">{t("engine")}</Text>
              <Text as="p" font="secondary-body" color="text-03">
                {t("stack")}
              </Text>
            </div>
          </section>
          <section className="flex min-w-0 flex-col gap-4 rounded-16 border border-border-01 bg-background-neutral-00 p-6">
            <div className="flex items-center gap-2">
              <SvgTerminal className="size-5" />
              <Text font="heading-h3">{t("journal")}</Text>
            </div>
            <div className="flex flex-wrap gap-2">
              {runs?.slice(0, 5).map((run) => (
                <Button
                  key={run.id}
                  prominence={active === run.id ? "primary" : "secondary"}
                  size="sm"
                  onClick={() => setSelected(run.id)}
                >{`${run.id.slice(0, 8)} · ${run.status}`}</Button>
              ))}
            </div>
            {!detail && <Text color="text-03">{t("noRun")}</Text>}
            {detail && (
              <>
                <div className="grid grid-cols-3 gap-3 border-y border-border-01 py-4">
                  <div>
                    <Text font="secondary-body" color="text-03">
                      {t("status")}
                    </Text>
                    <Text as="p" font="main-ui-action">
                      {detail.run.stage || detail.run.status}
                    </Text>
                  </div>
                  <div>
                    <Text font="secondary-body" color="text-03">
                      {t("checks")}
                    </Text>
                    <Text as="p" font="main-ui-action">
                      {detail.run.total
                        ? `${detail.run.passed} / ${detail.run.total}`
                        : "—"}
                    </Text>
                  </div>
                  <div>
                    <Text font="secondary-body" color="text-03">
                      {t("commit")}
                    </Text>
                    <Text as="p" font="main-ui-mono">
                      {detail.run.commit?.slice(0, 8) || "—"}
                    </Text>
                  </div>
                </div>
                <div className="max-h-96 overflow-y-auto">
                  {detail.events
                    .slice()
                    .reverse()
                    .map((event, i) => (
                      <div
                        key={`${event.at}-${i}`}
                        className="flex gap-3 border-b border-border-01 py-3"
                      >
                        <SvgCheckCircle className="mt-0.5 size-4 shrink-0 text-text-03" />
                        <div className="min-w-0">
                          <Text font="secondary-action">
                            {event.event.replaceAll("_", " ")}
                          </Text>
                          <div className="break-words">
                            <Text font="secondary-mono" color="text-03">
                              {JSON.stringify(
                                Object.fromEntries(
                                  Object.entries(event).filter(
                                    ([key]) =>
                                      !["at", "event", "sessions"].includes(key)
                                  )
                                )
                              )}
                            </Text>
                          </div>
                        </div>
                      </div>
                    ))}
                </div>
                {detail.run.error && (
                  <Text color="status-error-05">{detail.run.error}</Text>
                )}
                {detail.run.pr_url && (
                  <Button prominence="secondary" href={detail.run.pr_url}>
                    {t("pullRequest")}
                  </Button>
                )}
              </>
            )}
          </section>
        </div>
        <section className="flex min-w-0 flex-col gap-4 rounded-16 border border-border-01 bg-background-neutral-00 p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <Text as="h2" font="heading-h3">
              {t("inspect")}
            </Text>
            <div className="flex flex-wrap gap-1">
              {(
                ["evidence", "contract", "source", "tests", "agents"] as const
              ).map((item) => (
                <Button
                  key={item}
                  size="sm"
                  prominence={tab === item ? "secondary" : "tertiary"}
                  onClick={() => setTab(item)}
                >
                  {t(item)}
                </Button>
              ))}
            </div>
          </div>
          <pre
            className={cn(
              "max-h-[520px] overflow-auto rounded-12 bg-background-neutral-02 p-5 whitespace-pre-wrap break-words"
            )}
          >
            <Text font="secondary-mono">
              {!artifact || artifact === "null" ? t("pending") : artifact}
            </Text>
          </pre>
          <Text font="secondary-body" color="text-03">
            {t("boundary")}
          </Text>
        </section>
      </div>
    </div>
  );
}
