"use client";

/**
 * Database and API connections (plan 3.4).
 *
 * Until this page, StatFlow could only read files and scraped pages,
 * which capped it at personal-data analysis. A connection is the
 * missing ingest path: a Postgres database, a MySQL database, or a
 * REST endpoint returning JSON.
 *
 * Two things this page is careful about. First, the credential is
 * written once and never shown again -- the form asks for it, the
 * list says only whether one exists. Second, a sync is not a preview
 * overwrite: every pull writes a new immutable dataset version, so
 * the reader keeps every state of the data and the analysis history
 * stays honest about which version a result came from.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { Icon } from "@/components/Icon";
import { TextInput } from "@/components/Field";
import { TableSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import {
  apiErrorMessage,
  ConnectionPreview,
  ConnectionSyncRecord,
  DataConnection,
  statflowApi,
} from "@/lib/api";

const KIND_LABELS: Record<string, { label: string; fields: string[]; secret: string }> = {
  postgres: {
    label: "PostgreSQL",
    fields: ["host", "port", "database", "user", "table"],
    secret: "Nenosiri la database",
  },
  mysql: {
    label: "MySQL",
    fields: ["host", "port", "database", "user", "table"],
    secret: "Nenosiri la database",
  },
  rest: {
    label: "REST API (JSON)",
    fields: ["url"],
    secret: "Authorization header (hiari)",
  },
};

const OPTIONAL_FIELDS = new Set(["table"]);

export default function ConnectionsPage() {
  const { showToast } = useToast();
  const [connections, setConnections] = useState<DataConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [preview, setPreview] = useState<ConnectionPreview | null>(null);
  const [syncing, setSyncing] = useState<number | null>(null);
  const [history, setHistory] = useState<Record<number, ConnectionSyncRecord[]>>({});

  const [form, setForm] = useState({
    name: "",
    kind: "postgres",
    host: "",
    port: "5432",
    database: "",
    user: "",
    table: "",
    url: "",
    secret: "",
    sync_every_minutes: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await statflowApi.connections();
      setConnections(response.connections);
    } catch (cause) {
      showToast(apiErrorMessage(cause), "danger");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    load();
  }, [load]);

  async function create() {
    if (!form.name.trim()) {
      showToast("Andika jina la connection.", "warning");
      return;
    }
    setCreating(true);
    try {
      const kind = form.kind;
      const config: Record<string, unknown> =
        kind === "rest" ? { url: form.url.trim() } : {};
      if (kind !== "rest") {
        config.host = form.host.trim();
        config.port = Number(form.port || 5432);
        config.database = form.database.trim();
        config.user = form.user.trim();
        if (form.table.trim()) config.table = form.table.trim();
      }
      const created = await statflowApi.createConnection({
        name: form.name.trim(),
        kind,
        config,
        secret: form.secret || undefined,
        sync_every_minutes: form.sync_every_minutes
          ? Number(form.sync_every_minutes)
          : null,
        test: true,
      });
      const connection = created.connection;
      if (connection.status === "ok") {
        showToast("Connection imehifadhiwa na imethibitishwa.", "success");
        setPreview(null);
        setForm({ ...form, name: "", secret: "" });
        await load();
      } else {
        showToast(connection.last_error || "Connection haikuweza kuthibitishwa.", "danger");
      }
    } catch (cause) {
      showToast(apiErrorMessage(cause), "danger");
    } finally {
      setCreating(false);
    }
  }

  async function test(connection: DataConnection) {
    try {
      const result = await statflowApi.testConnection(connection.id);
      setPreview(result);
      showToast(`Connection inafanya kazi: ${result.row_count} rows.`, "success");
    } catch (cause) {
      setPreview(null);
      showToast(apiErrorMessage(cause), "danger");
    }
  }

  async function sync(connection: DataConnection) {
    setSyncing(connection.id);
    try {
      const result = await statflowApi.syncConnection(connection.id);
      showToast(
        result.queued
          ? "Sync imewekwa kwenye foleni."
          : `Sync imekamilika: v${result.dataset_version} · ${result.row_count} rows.`,
        "success"
      );
      const records = await statflowApi.connectionSyncs(connection.id);
      setHistory((previous) => ({ ...previous, [connection.id]: records.syncs }));
      await load();
    } catch (cause) {
      showToast(apiErrorMessage(cause), "danger");
    } finally {
      setSyncing(null);
    }
  }

  async function showHistory(connection: DataConnection) {
    if (history[connection.id]) {
      setHistory((previous) => {
        const next = { ...previous };
        delete next[connection.id];
        return next;
      });
      return;
    }
    try {
      const records = await statflowApi.connectionSyncs(connection.id);
      setHistory((previous) => ({ ...previous, [connection.id]: records.syncs }));
    } catch (cause) {
      showToast(apiErrorMessage(cause), "danger");
    }
  }

  async function remove(connection: DataConnection) {
    try {
      const result = await statflowApi.deleteConnection(connection.id);
      showToast(
        result.dataset_id
          ? "Connection imeondolewa; dataset iliyotengenezwa haijafutwa."
          : "Connection imeondolewa.",
        "success"
      );
      await load();
    } catch (cause) {
      showToast(apiErrorMessage(cause), "danger");
    }
  }

  const statusTone = (status: string) =>
    status === "ok" ? "success" : status === "error" ? "danger" : "neutral";

  return (
    <AppShell
      eyebrow="Unganisha data"
      title="Database na API za shirika"
      description="Unganisha PostgreSQL, MySQL au REST API. Kila sync huandika version mpya ya data — database yako haibadiliki, na kila matokeo yanabaki kuweza kurudiwa kwenye version yalivyotoka."
    >
      {loading && <TableSkeleton rows={3} />}

      {!loading && connections.length === 0 && (
        <EmptyState
          icon="database"
          title="Hakuna connection bado"
          description="Unganisha database au API ya shirika ili StatFlow isome data moja kwa moja, badala ya upakiaji wa faili kila wakati."
        />
      )}

      {!loading &&
        connections.map((connection) => (
          <Card key={connection.id}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex items-start gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-700">
                  <Icon name="database" size={18} />
                </span>
                <div>
                  <p className="text-body font-medium text-ink">{connection.name}</p>
                  <p className="mt-0.5 text-caption text-ink-muted">
                    {KIND_LABELS[connection.kind]?.label ?? connection.kind}
                    {connection.kind === "rest"
                      ? ` · ${String(connection.config.url ?? "")}`
                      : ` · ${String(connection.config.host ?? "")}:${String(
                          connection.config.port ?? ""
                        )}/${String(connection.config.database ?? "")}`}
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge tone={statusTone(connection.status) as "success" | "danger" | "neutral"}>
                  {connection.status === "ok"
                    ? "inafanya kazi"
                    : connection.status === "error"
                      ? "hitilafu"
                      : "haijapimwa"}
                </Badge>
                {connection.sync_every_minutes ? (
                  <Badge tone="info">kila {connection.sync_every_minutes} dakika</Badge>
                ) : null}
              </div>
            </div>

            {connection.last_error && (
              <p className="mt-2 flex items-start gap-1.5 rounded-md bg-danger-bg px-2.5 py-2 text-caption text-danger-700">
                <Icon name="alert-circle" size={13} className="mt-0.5 shrink-0" />
                {connection.last_error}
              </p>
            )}

            {connection.dataset_id && (
              <p className="mt-2 text-caption text-ink-muted">
                Inalisha{" "}
                <Link
                  href={`/datasets/${connection.dataset_id}`}
                  className="font-medium text-primary-700 hover:underline"
                >
                  dataset #{connection.dataset_id}
                </Link>
                {connection.last_sync_at && <> · sync ya mwisho {connection.last_sync_at.slice(0, 16).replace("T", " ")}</>}
              </p>
            )}

            <div className="mt-3 flex flex-wrap gap-2">
              <Button
                variant="secondary"
                size="small"
                icon="refresh"
                loading={syncing === connection.id}
                onClick={() => sync(connection)}
              >
                Sogeza sasa
              </Button>
              <Button
                variant="ghost"
                size="small"
                icon="search"
                onClick={() => test(connection)}
              >
                Pima
              </Button>
              <Button
                variant="ghost"
                size="small"
                icon="history"
                onClick={() => showHistory(connection)}
              >
                Historia
              </Button>
              <Button
                variant="ghost"
                size="small"
                icon="trash"
                onClick={() => remove(connection)}
              >
                Ondoa
              </Button>
            </div>

            {history[connection.id] && (
              <ul className="mt-3 divide-y divide-surface-border rounded-md border border-surface-border">
                {history[connection.id].length === 0 && (
                  <li className="px-3 py-2 text-caption text-ink-muted">
                    Hakuna sync bado.
                  </li>
                )}
                {history[connection.id].map((record) => (
                  <li
                    key={record.id}
                    className="flex flex-wrap items-center gap-2 px-3 py-2 text-caption"
                  >
                    <Badge
                      tone={record.status === "ok" ? "success" : "danger"}
                      size="sm"
                    >
                      {record.status}
                    </Badge>
                    <span className="text-ink">
                      {record.row_count.toLocaleString("en-KE")} rows
                    </span>
                    {record.dataset_version && (
                      <span className="text-ink-muted">v{record.dataset_version}</span>
                    )}
                    {record.duration_ms != null && (
                      <span className="text-ink-muted">{record.duration_ms} ms</span>
                    )}
                    {record.created_at && (
                      <span className="ml-auto text-ink-muted">
                        {record.created_at.slice(0, 16).replace("T", " ")}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        ))}

      <Card title="Ongeza connection" icon="plus">
        <div className="grid gap-3 sm:grid-cols-2">
          <TextInput
            label="Jina"
            value={form.name}
            placeholder="Mfano: Database ya wanachama"
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
          <label className="block text-caption text-ink-secondary">
            Aina
            <select
              value={form.kind}
              onChange={(event) => setForm({ ...form, kind: event.target.value })}
              className="mt-1 min-h-[40px] w-full rounded-md border border-surface-border bg-surface-panel px-2.5 text-body text-ink"
            >
              {Object.entries(KIND_LABELS).map(([kind, meta]) => (
                <option key={kind} value={kind}>
                  {meta.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {form.kind === "rest" ? (
          <div className="mt-3">
            <TextInput
              label="URL ya API"
              value={form.url}
              placeholder="https://api.shirika.org/v1/wanachama"
              onChange={(event) => setForm({ ...form, url: event.target.value })}
            />
          </div>
        ) : (
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {(["host", "port", "database", "user", "table"] as const).map((field) => (
              <TextInput
                key={field}
                label={field + (OPTIONAL_FIELDS.has(field) ? " (hiari)" : "")}
                value={form[field]}
                placeholder={field === "table" ? "wanachama" : undefined}
                onChange={(event) => setForm({ ...form, [field]: event.target.value })}
              />
            ))}
          </div>
        )}

        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <TextInput
            label={KIND_LABELS[form.kind].secret}
            type="password"
            value={form.secret}
            hint="Inahifadhiwa kwa usimbaji fiche na hairudishwi kamwe."
            onChange={(event) => setForm({ ...form, secret: event.target.value })}
          />
          <TextInput
            label="Sync otomatiki (dakika, hiari)"
            value={form.sync_every_minutes}
            placeholder="60"
            onChange={(event) =>
              setForm({ ...form, sync_every_minutes: event.target.value })
            }
          />
        </div>

        <div className="mt-4">
          <Button
            icon="check"
            loading={creating}
            onClick={create}
            className="min-h-[40px]"
          >
            Hifadhi na pima
          </Button>
          <p className="mt-2 text-caption text-ink-muted">
            Connection inapimwa mara moja kabla ya kuhifadhiwa, kosa la kuandika
            halitakaa kama synchroni isiyofanya kazi baadaye.
          </p>
        </div>
      </Card>

      {preview && (
        <Card title="Majaribio ya connection" icon="eye">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="success" size="md" icon="check">
              {preview.row_count.toLocaleString("en-KE")} rows
            </Badge>
            <span className="text-caption text-ink-muted">
              {preview.column_count} columns · {preview.elapsed_ms} ms
            </span>
          </div>
        </Card>
      )}
    </AppShell>
  );
}
