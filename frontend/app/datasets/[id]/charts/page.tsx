"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { ChartView } from "@/components/ChartView";
import { Skeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import {
  api,
  apiErrorMessage,
  ChartRecord,
  ChartType,
  ColumnProfile,
} from "@/lib/api";

const CHART_TYPE_OPTIONS: { value: ChartType; label: string; use: string }[] = [
  { value: "bar", label: "Bar chart", use: "Kulinganisha makundi" },
  { value: "line", label: "Line chart", use: "Mwenendo kwa muda" },
  { value: "scatter", label: "Scatter plot", use: "Uhusiano wa variables mbili" },
  { value: "histogram", label: "Histogram", use: "Mgawanyo wa data" },
];

const AGGREGATIONS = ["sum", "mean", "count", "min", "max", "median"] as const;

const SELECT_CLASSES =
  "h-10 w-full rounded border border-neutral-200 bg-white px-3 text-body outline-none focus:border-primary-500";

export default function ChartsPage() {
  const params = useParams<{ id: string }>();
  const datasetId = Number(params?.id);
  const { showToast } = useToast();

  const [columns, setColumns] = useState<ColumnProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [chartType, setChartType] = useState<ChartType>("bar");
  const [xColumn, setXColumn] = useState("");
  const [yColumn, setYColumn] = useState("");
  const [groupBy, setGroupBy] = useState("");
  const [aggregate, setAggregate] = useState<(typeof AGGREGATIONS)[number]>("sum");
  const [bins, setBins] = useState("20");
  const [creating, setCreating] = useState(false);
  const [current, setCurrent] = useState<ChartRecord | null>(null);
  const [saved, setSaved] = useState<ChartRecord[]>([]);

  const numericColumns = columns
    .filter((column) => column.data_type === "numeric")
    .map((column) => column.name);
  const allColumns = columns.map((column) => column.name);

  const loadSaved = useCallback(async () => {
    try {
      setSaved(await api.charts.listForDataset(datasetId));
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }, [datasetId, showToast]);

  useEffect(() => {
    async function load() {
      if (!Number.isFinite(datasetId)) return;
      setLoading(true);
      try {
        const detail = await api.datasets.get(datasetId);
        setColumns(detail.columns);
        const numeric = detail.columns
          .filter((column) => column.data_type === "numeric")
          .map((column) => column.name);
        setXColumn(detail.columns[0]?.name ?? "");
        setYColumn(numeric[0] ?? "");
        await loadSaved();
      } catch (caught) {
        showToast(apiErrorMessage(caught), "danger");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [datasetId, loadSaved, showToast]);

  async function createChart() {
    setCreating(true);
    try {
      const needsY = chartType === "bar" || chartType === "line";
      const record = await api.charts.create(datasetId, {
        chart_type: chartType,
        config: {
          x: xColumn,
          ...(chartType === "scatter" || (needsY && yColumn) ? { y: yColumn } : {}),
          ...(groupBy ? { group_by: groupBy } : {}),
          ...(needsY ? { aggregate } : {}),
          ...(chartType === "histogram" ? { bins: Number(bins) || 20 } : {}),
        },
      });
      setCurrent(record);
      showToast("Chati imetengenezwa", "success");
      await loadSaved();
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setCreating(false);
    }
  }

  return (
    <AppShell
      title="Chora chati"
      description="Chagua X na Y, aina ya chati, na uone preview papo hapo."
      actions={
        <>
          <Link href={`/datasets/${datasetId}`}>
            <Button variant="secondary">Angalia data</Button>
          </Link>
          <Link href={`/datasets/${datasetId}/export`}>
            <Button variant="secondary">Pakua ripoti</Button>
          </Link>
        </>
      }
    >
      <Card title="Mipangilio ya chati">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <label className="block text-body text-neutral-600" htmlFor="chart-type">
              Aina ya chati
            </label>
            <select
              id="chart-type"
              className={`${SELECT_CLASSES} mt-1`}
              value={chartType}
              onChange={(event) => setChartType(event.target.value as ChartType)}
            >
              {CHART_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label} — {option.use}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-body text-neutral-600" htmlFor="x-column">
              X axis
            </label>
            <select
              id="x-column"
              className={`${SELECT_CLASSES} mt-1`}
              value={xColumn}
              onChange={(event) => setXColumn(event.target.value)}
            >
              {allColumns.map((column) => (
                <option key={column} value={column}>
                  {column}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-body text-neutral-600" htmlFor="y-column">
              Y axis (numeric)
            </label>
            <select
              id="y-column"
              className={`${SELECT_CLASSES} mt-1`}
              value={yColumn}
              onChange={(event) => setYColumn(event.target.value)}
              disabled={chartType === "histogram"}
            >
              <option value="">— count ya rows —</option>
              {numericColumns.map((column) => (
                <option key={column} value={column}>
                  {column}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-body text-neutral-600" htmlFor="group-by">
              Group by (si lazima)
            </label>
            <select
              id="group-by"
              className={`${SELECT_CLASSES} mt-1`}
              value={groupBy}
              onChange={(event) => setGroupBy(event.target.value)}
            >
              <option value="">— Hakuna —</option>
              {allColumns.map((column) => (
                <option key={column} value={column}>
                  {column}
                </option>
              ))}
            </select>
          </div>

          {(chartType === "bar" || chartType === "line") && (
            <div>
              <label className="block text-body text-neutral-600" htmlFor="aggregate">
                Hesabu (aggregate)
              </label>
              <select
                id="aggregate"
                className={`${SELECT_CLASSES} mt-1`}
                value={aggregate}
                onChange={(event) =>
                  setAggregate(event.target.value as (typeof AGGREGATIONS)[number])
                }
              >
                {AGGREGATIONS.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
          )}

          {chartType === "histogram" && (
            <div>
              <label className="block text-body text-neutral-600" htmlFor="bins">
                Idadi ya bins
              </label>
              <input
                id="bins"
                className={`${SELECT_CLASSES} mt-1`}
                value={bins}
                onChange={(event) => setBins(event.target.value)}
              />
            </div>
          )}
        </div>

        <Button className="mt-4" size="large" loading={creating} onClick={createChart}>
          Tengeneza chati
        </Button>
      </Card>

      <Card
        title="Preview ya chati"
        description={current ? `${current.chart_type} chart` : "Chati itaonekana hapa"}
      >
        {loading ? (
          <Skeleton className="h-[380px] w-full" />
        ) : (
          <ChartView data={current?.chart_data ?? null} />
        )}
      </Card>

      <Card
        title="Chati zilizohifadhiwa"
        description="Chati zote ulizotengeneza kwa dataset hii — unaweza kuzijumuisha kwenye ripoti."
      >
        {saved.length === 0 ? (
          <EmptyState title="Hakuna chati iliyohifadhiwa" />
        ) : (
          <ul className="grid gap-3 lg:grid-cols-2">
            {saved.map((record) => (
              <li key={record.chart_id} className="rounded border border-neutral-200 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="flex items-center gap-2">
                    <Badge tone="primary">{record.chart_type}</Badge>
                    <span className="text-caption text-neutral-600">
                      x: {record.config.x}
                      {record.config.y ? ` · y: ${record.config.y}` : ""}
                      {record.config.group_by
                        ? ` · group: ${record.config.group_by}`
                        : ""}
                    </span>
                  </span>
                  <Button
                    variant="ghost"
                    size="small"
                    onClick={() => setCurrent(record)}
                  >
                    Onyesha
                  </Button>
                </div>
                <div className="mt-2">
                  <ChartView data={record.chart_data} height={200} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

    </AppShell>
  );
}
