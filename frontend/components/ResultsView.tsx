"use client";

import { Badge } from "@/components/Badge";
import { DataTable } from "@/components/DataTable";

interface ResultsViewProps {
  analysisType: string;
  result: Record<string, any>;
}

function NumericTable({
  rows,
  numericColumns,
  caption,
}: {
  rows: Record<string, any>[];
  numericColumns: string[];
  caption: string;
}) {
  if (!rows || rows.length === 0) {
    return <p className="text-body text-neutral-600">Hakuna matokeo.</p>;
  }
  return (
    <DataTable
      caption={caption}
      columns={Object.keys(rows[0])}
      rows={rows}
      numericColumns={numericColumns}
    />
  );
}

function CorrelationMatrix({
  columns,
  matrix,
}: {
  columns: string[];
  matrix: (number | null)[][];
}) {
  const rows = matrix.map((row, index) => {
    const entry: Record<string, unknown> = { variable: columns[index] };
    columns.forEach((column, columnIndex) => {
      entry[column] = row[columnIndex];
    });
    return entry;
  });

  return (
    <DataTable
      caption="Correlation matrix"
      columns={["variable", ...columns]}
      rows={rows}
      numericColumns={columns}
      renderCell={(_, value) => {
        const numeric = typeof value === "number" ? value : null;
        if (numeric === null) return "—";
        // Positive correlations tint blue, negative tint red; the number is
        // always printed so meaning never depends on colour alone.
        const intensity = Math.min(Math.abs(numeric), 1) * 0.35;
        const background =
          numeric >= 0
            ? `rgba(37, 99, 235, ${intensity})`
            : `rgba(220, 38, 38, ${intensity})`;
        return (
          <span
            className="inline-block w-full rounded px-1"
            style={{ backgroundColor: background }}
          >
            {numeric.toFixed(4)}
          </span>
        );
      }}
    />
  );
}

/** Renders a stored analysis result according to its type. */
export function ResultsView({ analysisType, result }: ResultsViewProps) {
  if (analysisType === "descriptive_stats") {
    return (
      <div className="space-y-4">
        <div>
          <p className="text-h3 text-neutral-900">Numeric variables</p>
          <div className="mt-2">
            <NumericTable
              caption="Descriptive statistics for numeric columns"
              rows={result.numeric_stats ?? []}
              numericColumns={[
                "count",
                "missing",
                "mean",
                "median",
                "mode",
                "std_dev",
                "variance",
                "min",
                "q1",
                "q3",
                "max",
                "sum",
              ]}
            />
          </div>
        </div>
        <div>
          <p className="text-h3 text-neutral-900">Categorical variables</p>
          <div className="mt-2">
            <NumericTable
              caption="Descriptive statistics for categorical columns"
              rows={result.categorical_stats ?? []}
              numericColumns={[
                "count",
                "missing",
                "unique",
                "top_frequency",
                "top_percentage",
              ]}
            />
          </div>
        </div>
      </div>
    );
  }

  if (analysisType === "correlation") {
    return (
      <div className="space-y-4">
        <p className="text-body text-neutral-600">
          Method: <span className="font-mono">{result.method}</span> · columns{" "}
          {(result.columns ?? []).length} · rows {result.row_count}
        </p>
        <CorrelationMatrix columns={result.columns ?? []} matrix={result.matrix ?? []} />
        <div>
          <p className="text-h3 text-neutral-900">Uhusiano wenye nguvu</p>
          <div className="mt-2">
            <NumericTable
              caption="Strongest correlation pairs"
              rows={(result.pairs ?? []).slice(0, 10)}
              numericColumns={["coefficient"]}
            />
          </div>
        </div>
      </div>
    );
  }

  if (analysisType === "regression") {
    const coefficients = Object.entries(
      (result.coefficients ?? {}) as Record<string, number>
    ).map(([variable, coefficient]) => ({ variable, coefficient }));
    return (
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="rounded border border-neutral-200 bg-neutral-50 p-3">
            <p className="text-caption uppercase text-neutral-600">R-squared</p>
            <p className="numeric-table text-h2">{result.r_squared}</p>
          </div>
          <div className="rounded border border-neutral-200 bg-neutral-50 p-3">
            <p className="text-caption uppercase text-neutral-600">Observations</p>
            <p className="numeric-table text-h2">{result.n_observations}</p>
          </div>
          <div className="rounded border border-neutral-200 bg-neutral-50 p-3">
            <p className="text-caption uppercase text-neutral-600">Std. error</p>
            <p className="numeric-table text-h2">{result.std_error ?? "—"}</p>
          </div>
        </div>
        <p className="rounded bg-info-bg px-3 py-2 font-mono text-body text-info">
          {result.equation}
        </p>
        <NumericTable
          caption="Regression coefficients"
          rows={coefficients}
          numericColumns={["coefficient"]}
        />
        <div>
          <p className="text-h3 text-neutral-900">Predictions (mfano)</p>
          <div className="mt-2">
            <NumericTable
              caption="Predicted vs actual values"
              rows={(result.predictions_preview ?? []).slice(0, 10)}
              numericColumns={["actual", "predicted", "residual"]}
            />
          </div>
        </div>
      </div>
    );
  }

  if (analysisType === "hypothesis_test") {
    const groups = Object.entries(
      (result.groups ?? {}) as Record<string, unknown>
    ).map(([group, value]) => ({
      group,
      value: typeof value === "object" ? JSON.stringify(value) : value,
    }));
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <Badge tone={result.significant ? "danger" : "success"} withIcon>
            {result.significant
              ? "Tofauti ni significant"
              : "Hakuna tofauti significant"}
          </Badge>
          <span className="text-body text-neutral-600">
            {result.test} · t = <span className="font-mono">{result.t_statistic}</span>{" "}
            · p = <span className="font-mono">{result.p_value}</span> · df ={" "}
            <span className="font-mono">{result.degrees_of_freedom}</span>
          </span>
        </div>
        <p className="rounded bg-neutral-100 px-3 py-2 text-body text-neutral-900">
          {result.interpretation}
        </p>
        <NumericTable caption="Group statistics" rows={groups} numericColumns={[]} />
      </div>
    );
  }

  return (
    <pre className="overflow-x-auto rounded bg-neutral-100 p-3 text-caption">
      {JSON.stringify(result, null, 2)}
    </pre>
  );
}

export default ResultsView;
