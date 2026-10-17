"use client";

import { useState } from "react";
import { useFormatter, useTranslations } from "next-intl";
import { Button, InputTypeIn, Text } from "@opal/components";

export interface NativeTrace {
  captured_at?: string;
  error?: string;
  truncated?: boolean;
  sessions: {
    id: string;
    parent_session_id: string | null;
    model: string;
    api_call_count: number;
  }[];
  entries: {
    id: string;
    session: string;
    at: number;
    kind: string;
    name: string;
    content: string;
    truncated: boolean;
  }[];
}

export default function RunTrace({
  trace,
  running,
}: {
  trace?: NativeTrace;
  running: boolean;
}) {
  const t = useTranslations("aya");
  const format = useFormatter();
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState(false);
  const entries = (trace?.entries || []).filter((entry) =>
    `${entry.name} ${entry.content}`
      .toLowerCase()
      .includes(filter.toLowerCase())
  );
  const sessions = trace?.sessions || [];
  const calls = sessions.reduce(
    (total, session) => total + (session.api_call_count || 0),
    0
  );
  const children = new Set(
    sessions
      .filter((session) => session.parent_session_id)
      .map((session) => session.id)
  );
  return (
    <div className="flex min-w-0 flex-col gap-3 border-t border-border-01 pt-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Text as="h3" font="main-ui-action">
            {t("traceTitle")}
          </Text>
          <Text as="p" font="secondary-body" color="text-03">
            {t(running && calls === 0 ? "traceCountsPending" : "traceCounts", {
              calls,
              children: children.size,
              events: trace?.entries.length || 0,
            })}
          </Text>
        </div>
        <Button
          size="sm"
          prominence="secondary"
          onClick={() => setExpanded(!expanded)}
        >
          {t(expanded ? "hideTrace" : "showTrace")}
        </Button>
      </div>
      <Text as="p" font="secondary-body" color="text-03">
        {t("traceNote")}
      </Text>
      {expanded && (
        <>
          <InputTypeIn
            aria-label={t("traceFilter")}
            placeholder={t("traceFilter")}
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
          />
          {trace?.error && <Text color="status-error-05">{trace.error}</Text>}
          {entries.length === 0 && (
            <Text color="text-03">
              {t(running ? "traceWaiting" : "traceEmpty")}
            </Text>
          )}
          <div className="max-h-[480px] overflow-y-auto rounded-12 border border-border-01">
            {entries.map((entry) => (
              <details
                key={`${entry.session}-${entry.id}`}
                className="border-b border-border-01 p-3 last:border-0"
              >
                <summary className="cursor-pointer break-words">
                  <Text font="secondary-mono" color="text-03">
                    {format.dateTime(new Date(entry.at * 1000), {
                      hour: "numeric",
                      minute: "numeric",
                      second: "numeric",
                    })}
                  </Text>{" "}
                  <Text font="secondary-action">{entry.name}</Text>{" "}
                  <Text font="secondary-body" color="text-03">
                    {`${t(children.has(entry.session) ? "traceChild" : "traceWorker")} · ${entry.kind}`}
                  </Text>
                </summary>
                <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words pt-3">
                  <Text font="secondary-mono">{entry.content}</Text>
                </pre>
                {entry.truncated && (
                  <Text font="secondary-body" color="text-03">
                    {t("traceTruncated")}
                  </Text>
                )}
              </details>
            ))}
          </div>
          {trace?.captured_at && (
            <Text font="secondary-body" color="text-03">
              {t("traceUpdated", {
                time: format.dateTime(new Date(trace.captured_at), {
                  hour: "numeric",
                  minute: "numeric",
                  second: "numeric",
                }),
              })}
            </Text>
          )}
        </>
      )}
    </div>
  );
}
