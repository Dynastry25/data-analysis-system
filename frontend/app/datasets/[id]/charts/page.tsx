"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { ChartView } from "@/components/ChartView";
import { SelectInput, TextInput } from "@/components/Field";
import { Skeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import {
  api,
  apiErrorMessage,
  ChartFormat,
  ChartPaletteName,
  ChartRecord,
  ChartType,
  ColumnProfile,
} from "@/lib/api";
import { CHART_PALETTES } from "@/lib/constants";

const CHART_TYPE_OPTIONS: { value: ChartType; label: string; use: string }[] = [
  { value: "bar", label: "Chati ya mistari", use: "Kulinganisha makundi" },
  { value: "line", label: "Chati ya mstari", use: "Mwenendo kwa muda" },
  { value: "scatter", label: "Chati ya alama", use: "Uhusiano wa variables mbili" },
  { value: "histogram", label: "Histograma", use: "Mgawanyo wa data" },
];

const AGGREGATION_LABELS: Record<string, string> = {
  sum: "Jumla",
  mean: "Wastani",
  count: "Idadi",
  min: "Chini kabisa",
  max: "Juu kabisa",
  median: "Mediani",
};

const AGGREGATIONS = ["sum", "mean", "count", "min", "max", "median"] as const;

const SCALE_OPTIONS = [
  { value: "linear", label: "Linear" },
  { value: "log", label: "Log" },
];

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
  const [format, setFormat] = useState<ChartFormat>({
    palette: "default",
    show_data_labels: true,
    show_grid: true,
    x_scale: "linear",
    y_scale: "linear",
  });

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
          ...(format ? { format } : {}),
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
      title="Visualization Studio"
      description="Chagua X na Y, aina ya chati, na uone preview papo hapo."
      actions={
        <>
          <Link href={`/datasets/${datasetId}`}>
            <Button variant="secondary">Angalia data</Button>
          </Link>
          <Link href={`/datasets/${datasetId}/dashboard`}>
            <Button variant="secondary">Dashboard Builder</Button>
          </Link>
          <Link href={`/datasets/${datasetId}/export`}>
            <Button variant="secondary">Pakua ripoti</Button>
          </Link>
        </>
      }
    >
      <Card title="Mipangilio ya chati" icon="chart">
        <p className="mb-3 text-overline uppercase tracking-wide text-ink-muted">
          Variable mapping
        </p>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <SelectInput
            label="Aina ya chati"
            value={chartType}
            hint={CHART_TYPE_OPTIONS.find((option) => option.value === chartType)?.use}
            options={CHART_TYPE_OPTIONS.map((option) => ({
              value: option.value,
              label: `${option.label} — ${option.use}`,
            }))}
            onChange={(event) => setChartType(event.target.value as ChartType)}
          />

          <SelectInput
            label="X axis"
            value={xColumn}
            required
            options={allColumns.map((column) => ({ value: column, label: column }))}
            onChange={(event) => setXColumn(event.target.value)}
          />

          <SelectInput
            label="Y axis (numeric)"
            value={yColumn}
            optionalLabel={chartType === "histogram" ? "haitumiki" : "hiari"}
            disabled={chartType === "histogram"}
            placeholder="— count ya rows —"
            options={numericColumns.map((column) => ({ value: column, label: column }))}
            onChange={(event) => setYColumn(event.target.value)}
          />

          <SelectInput
            label="Group by"
            optionalLabel="hiari"
            placeholder="— Hakuna —"
            value={groupBy}
            options={allColumns.map((column) => ({ value: column, label: column }))}
            onChange={(event) => setGroupBy(event.target.value)}
          />

          {chartType === "bar" || chartType === "line" ? (
            <SelectInput
              label="Hesabu (aggregate)"
              value={aggregate}
              options={AGGREGATIONS.map((item) => ({
                value: item,
                label: AGGREGATION_LABELS[item] ?? item,
              }))}
              onChange={(event) =>
                setAggregate(event.target.value as (typeof AGGREGATIONS)[number])
              }
            />
          ) : null}

          {chartType === "histogram" ? (
            <TextInput
              label="Idadi ya bins"
              type="number"
              min={2}
              max={200}
              value={bins}
              onChange={(event) => setBins(event.target.value)}
            />
          ) : null}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button
            size="large"
            loading={creating}
            onClick={createChart}
            disabled={!xColumn}
            icon="chart"
          >
            Tengeneza chati
          </Button>
          <span className="text-caption text-ink-muted">
            Chati zinatengenezwa kwa version ya sasa ya dataset
          </span>
        </div>
      </Card>

      <Card title="Chanzo & Muundo" description="Palette na format zina jinsi chati inavyowasilishwa, sio takwimu zake." icon="sliders">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <p className="mb-1.5 text-body font-medium text-ink">Palette ya rangi</p>
            <div className="flex flex-wrap gap-2">
              {(Object.keys(CHART_PALETTES) as ChartPaletteName[]).map((name) => {
                const active = (format.palette ?? "default") === name;
                return (
                  <button
                    key={name}
                    type="button"
                    aria-pressed={active}
                    className={`flex items-center gap-2 rounded-pill border px-2.5 py-1 text-caption transition-colors ${
                      active
                        ? "border-primary-300 bg-primary-50 font-medium text-primary-800"
                        : "border-surface-border bg-surface-panel text-ink-secondary hover:bg-surface-sunken"
                    }`}
                    onClick={() => setFormat((previous) => ({ ...previous, palette: name }))}
                  >
                    <span className="flex gap-0.5">
                      {CHART_PALETTES[name].colors.slice(0, 4).map((color) => (
                        <span
                          key={color}
                          className="h-3 w-3 rounded-full border border-black/10"
                          style={{ backgroundColor: color }}
                        />
                      ))}
                    </span>
                    {CHART_PALETTES[name].label}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <p className="mb-1.5 text-body font-medium text-ink">Kuonekana</p>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                aria-pressed={format.show_data_labels !== false}
                className={`rounded-pill border px-2.5 py-1 text-caption transition-colors ${
                  format.show_data_labels !== false
                    ? "border-primary-300 bg-primary-50 font-medium text-primary-800"
                    : "border-surface-border bg-surface-panel text-ink-secondary hover:bg-surface-sunken"
                }`}
                onClick={() =>
                  setFormat((previous) => ({
                    ...previous,
                    show_data_labels: previous.show_data_labels === false,
                  }))
                }
              >
                Labels za data
              </button>
              <button
                type="button"
                aria-pressed={format.show_grid !== false}
                className={`rounded-pill border px-2.5 py-1 text-caption transition-colors ${
                  format.show_grid !== false
                    ? "border-primary-300 bg-primary-50 font-medium text-primary-800"
                    : "border-surface-border bg-surface-panel text-ink-secondary hover:bg-surface-sunken"
                }`}
                onClick={() =>
                  setFormat((previous) => ({
                    ...previous,
                    show_grid: previous.show_grid === false,
                  }))
                }
              >
                Gridlines
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <SelectInput
              label="Scale ya X"
              value={format.x_scale ?? "linear"}
              options={SCALE_OPTIONS}
              onChange={(event) =>
                setFormat((previous) => ({
                  ...previous,
                  x_scale: event.target.value as ChartFormat["x_scale"],
                }))
              }
            />
            <SelectInput
              label="Scale ya Y"
              value={format.y_scale ?? "linear"}
              options={SCALE_OPTIONS}
              onChange={(event) =>
                setFormat((previous) => ({
                  ...previous,
                  y_scale: event.target.value as ChartFormat["y_scale"],
                }))
              }
            />
          </div>
        </div>
        <p className="mt-3 text-caption text-ink-muted">
          Mapendeleo yanahifadhiwa pamoja na chati kila unapotengeneza. Rangi zinarudishwa
          kwa kundi moja kila chati ya dataset hii.
        </p>
      </Card>

      <Card
        title="Preview ya chati"
        description={current ? `${current.chart_type} chart` : "Chati itaonekana hapa"}
        icon="chart"
      >
        {loading ? (
          <Skeleton className="h-[380px] w-full" />
        ) : (
          <ChartView data={current?.chart_data ?? null} format={format} />
        )}
      </Card>

      <Card
        title="Chati zilizohifadhiwa"
        description="Chati zote ulizotengeneza kwa dataset hii unaweza kuzijumuisha kwenye ripoti."
        icon="layers"
      >
        {saved.length === 0 ? (
          <EmptyState
            title="Hakuna chati iliyohifadhiwa"
            description="Chagua columns hapa juu kisha bonyeza Tengeneza chati. Chati zote zinabaki na toleo la data ulizotumia."
            icon="chart"
          />
        ) : (
          <ul className="grid gap-3 lg:grid-cols-2">
            {saved.map((record) => (
              <li
                key={record.chart_id}
                className="rounded-md border border-surface-border p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="flex flex-wrap items-center gap-2">
                    <Badge tone="primary" icon="chart">
                      {record.chart_type}
                    </Badge>
                    <span className="text-caption text-ink-muted">
                      <span className="font-mono font-medium text-ink">
                        v{record.dataset_version}
                      </span>{" "}
                      · x: {record.config.x}
                      {record.config.y ? ` · y: ${record.config.y}` : ""}
                      {record.config.group_by
                        ? ` · group: ${record.config.group_by}`
                        : ""}
                    </span>
                  </span>
                  <Button
                    variant="secondary"
                    size="small"
                    icon="table"
                    onClick={() => {
                      setCurrent(record);
                      if (record.config.format) setFormat(record.config.format);
                    }}
                  >
                    Onyesha
                  </Button>
                </div>
                <div className="mt-2">
                  <ChartView
                    data={record.chart_data}
                    height={200}
                    format={record.config.format ?? null}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </AppShell>
  );
}
