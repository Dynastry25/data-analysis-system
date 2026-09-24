"use client";

import { Badge } from "@/components/Badge";
import { DataTable } from "@/components/DataTable";
import {
  CollapsibleDetails,
  GroupBars,
  InterpretationBox,
  MetricCard,
  fmt,
  pFmt,
} from "@/components/StandardResultView";

interface ResultsViewProps {
  analysisType: string;
  result: Record<string, any>;
}

/** English strength labels from the backend → Swahili (design system §4). */
const STRENGTH_SW: Record<string, string> = {
  "very strong": "imara sana",
  strong: "imara",
  moderate: "wastani",
  weak: "dhaifu",
  "very weak": "dhaifu sana",
};

function strengthSw(label: unknown): string {
  return STRENGTH_SW[String(label)] ?? String(label ?? "");
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
        // always printed so meaning never depends on colour alone (§11).
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

/** Layer 1 — plain-language headline + badges. */
function Headline({
  text,
  children,
}: {
  text: string;
  children?: React.ReactNode;
}) {
  return (
    <div>
      <p className="text-body-lg text-neutral-900">{text}</p>
      {children && (
        <div className="mt-2 flex flex-wrap items-center gap-2">{children}</div>
      )}
    </div>
  );
}

/** Layer 2 — row of key-number metric cards. */
function MetricsRow({
  metrics,
}: {
  metrics: { label: string; value: string; hint?: string }[];
}) {
  const visible = metrics.filter(
    (metric) => metric.value !== "—" && metric.value !== ""
  );
  if (visible.length === 0) return null;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {visible.map((metric) => (
        <MetricCard key={metric.label} {...metric} />
      ))}
    </div>
  );
}

/** Layer 3 — panel wrapping visuals. */
function VisualPanel({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded border border-neutral-200 bg-neutral-50 p-4">
      {children}
    </div>
  );
}

/** Renders a stored analysis result with progressive disclosure (design system §10). */
export function ResultsView({ analysisType, result }: ResultsViewProps) {
  if (analysisType === "descriptive_stats") {
    const numericStats = (result.numeric_stats ?? []) as Record<string, any>[];
    const categoricalStats = (result.categorical_stats ?? []) as Record<string, any>[];
    const meanBars = numericStats
      .filter((row) => typeof row.mean === "number" && Number.isFinite(row.mean))
      .slice(0, 8)
      .map((row) => ({ label: String(row.column), value: row.mean as number }));
    const mostVariable = numericStats
      .filter((row) => typeof row.std_dev === "number")
      .sort((a, b) => b.std_dev - a.std_dev)[0];

    return (
      <div className="space-y-6">
        <Headline
          text={`Muhtasari wa takwimu: columns ${numericStats.length} za namba na ${categoricalStats.length} za makundi, kutoka rows ${result.row_count ?? "—"}.`}
        >
          <Badge tone="primary">descriptive_stats</Badge>
        </Headline>

        {meanBars.length > 0 && (
          <VisualPanel>
            <GroupBars
              values={meanBars}
              title="Wastani (mean) wa columns za namba"
            />
          </VisualPanel>
        )}

        <CollapsibleDetails label="Angalia zaidi — takwimu kamili za kila column">
          <div>
            <p className="text-h3 text-neutral-900">Numeric variables</p>
            <div className="mt-2">
              <NumericTable
                caption="Descriptive statistics for numeric columns"
                rows={numericStats}
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
                rows={categoricalStats}
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
        </CollapsibleDetails>

        <InterpretationBox>
          {mostVariable
            ? `Column yenye mabadiliko makubwa zaidi ni "${mostVariable.column}" (std dev = ${fmt(mostVariable.std_dev)}) — thamani zake zimetawanyika zaidi kuliko nyingine. Linganisha mean na median: zikilengana sana data imesawazika; zikitofautiana kuna skew.`
            : "Huu ni muhtasari wa msingi wa data yako — fungua 'Angalia zaidi' kuona takwimu kamili za kila column."}
        </InterpretationBox>
      </div>
    );
  }

  if (analysisType === "correlation") {
    const pairs = (result.pairs ?? []) as Record<string, any>[];
    const top = pairs[0];

    return (
      <div className="space-y-6">
        <Headline
          text={
            top
              ? `Uhusiano imara zaidi ni kati ya "${top.column_a}" na "${top.column_b}" (r = ${fmt(top.coefficient)}, ${strengthSw(top.strength)}).`
              : "Hakuna pairs za kutosha kupima uhusiano."
          }
        >
          <Badge tone="primary">correlation · {result.method}</Badge>
          <Badge tone="neutral">columns {(result.columns ?? []).length}</Badge>
          <Badge tone="neutral">n = {result.row_count ?? "—"}</Badge>
        </Headline>

        <MetricsRow
          metrics={[
            ...(top
              ? [
                  {
                    label: "r (ya juu kabisa)",
                    value: fmt(top.coefficient),
                    hint: `${top.column_a} ~ ${top.column_b}`,
                  },
                ]
              : []),
            {
              label: "Pairs",
              value: String(pairs.length),
              hint: "miunganisho yote",
            },
          ]}
        />

        {pairs.length > 0 && (
          <VisualPanel>
            <GroupBars
              title="Nguvu ya uhusiano (r) — pairs 5 za juu"
              values={pairs.slice(0, 5).map((pair) => ({
                label: `${pair.column_a} ~ ${pair.column_b}`,
                value: Number(pair.coefficient),
              }))}
            />
          </VisualPanel>
        )}

        <CollapsibleDetails label="Angalia zaidi — correlation matrix kamili na pairs zote">
          <CorrelationMatrix
            columns={result.columns ?? []}
            matrix={result.matrix ?? []}
          />
          <NumericTable
            caption="Strongest correlation pairs"
            rows={pairs.slice(0, 10)}
            numericColumns={["coefficient"]}
          />
        </CollapsibleDetails>

        <InterpretationBox>
          {top
            ? `r karibu na +1 au -1 ina maana columns hizi hubadilika pamoja kwa nguvu (${strengthSw(top.strength)}); r karibu na 0 ina maana hazihusiani. Kumbuka: uhusiano hauthibitishi sababu — inawezekana variable nyingine ndiyo inayowaendesha zote mbili.`
            : "Ongeza columns za namba (angalau 2) ili kupima uhusiano."}
        </InterpretationBox>
      </div>
    );
  }

  if (analysisType === "regression") {
    const coefficients = Object.entries(
      (result.coefficients ?? {}) as Record<string, number>
    ).map(([variable, coefficient]) => ({ variable, coefficient }));
    const byImpact = [...coefficients].sort(
      (a, b) => Math.abs(b.coefficient) - Math.abs(a.coefficient)
    );
    const topFeature = byImpact[0];
    const r2 = typeof result.r_squared === "number" ? result.r_squared : null;
    const r2Pct = r2 !== null ? Math.round(r2 * 1000) / 10 : null;

    return (
      <div className="space-y-6">
        <Headline
          text={
            r2Pct !== null
              ? `Modeli inaelezea ${r2Pct}% ya mabadiliko ya "${result.target}" (R² = ${fmt(r2)}).`
              : "Modeli ya regression imekamilika."
          }
        >
          <Badge tone="primary">regression</Badge>
          <Badge tone="neutral">target: {result.target}</Badge>
        </Headline>

        <MetricsRow
          metrics={[
            { label: "R²", value: fmt(result.r_squared), hint: "% inayoelezwa" },
            { label: "Adj. R²", value: fmt(result.adjusted_r_squared) },
            {
              label: "n",
              value: fmt(result.n_observations),
              hint: "observations",
            },
            {
              label: "Std. error",
              value: fmt(result.std_error),
              hint: "kosa la wastani",
            },
          ]}
        />

        {byImpact.length > 0 && (
          <VisualPanel>
            <GroupBars
              title="Ushawishi wa features (coefficients)"
              values={byImpact.slice(0, 8).map((entry) => ({
                label: entry.variable,
                value: entry.coefficient,
              }))}
            />
          </VisualPanel>
        )}

        <CollapsibleDetails label="Angalia zaidi — equation, coefficients na predictions">
          <p className="rounded bg-info-bg px-3 py-2 font-mono text-body text-info">
            {result.equation}
          </p>
          <NumericTable
            caption="Regression coefficients"
            rows={coefficients}
            numericColumns={["coefficient"]}
          />
          <NumericTable
            caption="Predicted vs actual values"
            rows={(result.predictions_preview ?? []).slice(0, 10)}
            numericColumns={["actual", "predicted", "residual"]}
          />
        </CollapsibleDetails>

        <InterpretationBox>
          {topFeature
            ? `Feature yenye ushawishi mkubwa zaidi kwa "${result.target}" ni "${topFeature.variable}" (coefficient = ${fmt(topFeature.coefficient)})${topFeature.coefficient >= 0 ? ": inapoongezeka, target huongezeka" : ": inapoongezeka, target hupungua"}. R² ya ${fmt(result.r_squared)} ina maana modeli inaelezea ${r2Pct}% ya mabadiliko — ${r2 !== null && r2 >= 0.7 ? "kiwango kizuri" : r2 !== null && r2 >= 0.4 ? "wastani" : "kidogo; fikiria kuongeza features nyingine"}.`
            : "Fungua 'Angalia zaidi' kuona equation kamili ya modeli."}
        </InterpretationBox>
      </div>
    );
  }

  if (analysisType === "hypothesis_test") {
    const groups = Object.entries(
      (result.groups ?? {}) as Record<string, unknown>
    );
    const groupRows = groups.map(([group, value]) =>
      typeof value === "object" && value !== null
        ? { group, ...(value as Record<string, unknown>) }
        : { group, value }
    );
    const meanBars = groups
      .filter(
        ([, value]) =>
          typeof value === "object" &&
          value !== null &&
          typeof (value as Record<string, unknown>).mean === "number"
      )
      .map(([label, value]) => ({
        label,
        value: (value as Record<string, number>).mean,
      }));
    const significant = result.significant === true;
    const alpha = result.alpha ?? 0.05;

    return (
      <div className="space-y-6">
        <Headline
          text={
            significant
              ? `Tofauti ni muhimu kiotakwimu (${result.test}, p = ${pFmt(result.p_value)}) — kuna ushahidi wa kutosha.`
              : `Hakuna tofauti muhimu kiotakwimu (${result.test}, p = ${pFmt(result.p_value)}) — ushahidi hautoshi.`
          }
        >
          <Badge tone="primary">{result.test}</Badge>
          <Badge tone={significant ? "success" : "neutral"} withIcon>
            Umuhimu wa kitakwimu: {significant ? "Ndiyo" : "Hapana"}
          </Badge>
        </Headline>

        <MetricsRow
          metrics={[
            { label: "t statistic", value: fmt(result.t_statistic) },
            {
              label: "p-value",
              value: pFmt(result.p_value),
              hint: `alpha = ${alpha}`,
            },
            {
              label: "df",
              value: fmt(result.degrees_of_freedom),
              hint: "degrees of freedom",
            },
          ]}
        />

        {meanBars.length >= 2 && (
          <VisualPanel>
            <GroupBars title="Wastani (mean) wa makundi" values={meanBars} />
          </VisualPanel>
        )}

        <CollapsibleDetails label="Angalia zaidi — hypothesis na takwimu za makundi">
          <p className="text-body text-neutral-600">
            Hypothesis:{" "}
            <span className="font-mono">{String(result.hypothesis ?? "")}</span>
            {result.alternative ? ` · alternative: ${result.alternative}` : ""}
          </p>
          <NumericTable
            caption="Group statistics"
            rows={groupRows}
            numericColumns={["n", "mean", "std_dev", "value"]}
          />
        </CollapsibleDetails>

        <InterpretationBox>
          {significant
            ? `Kwa kuwa p = ${pFmt(result.p_value)} ni chini ya alpha = ${alpha}, tuna ushahidi wa kutosha kwamba tofauti ni ya kweli katika data hii — si bahati tu. Angalia wastani wa makundi hapo juu kuona mwelekeo wa tofauti.`
            : `Kwa kuwa p = ${pFmt(result.p_value)} si chini ya alpha = ${alpha}, hatuna ushahidi wa kutosha kusema tofauti ipo — inawezekana ni bahati au sample ndogo. Ongeza data au jaribu alpha kubwa zaidi kwa makadirio tu.`}
        </InterpretationBox>
      </div>
    );
  }

  return (
    <pre className="overflow-x-auto rounded bg-neutral-100 p-3 font-mono text-caption">
      {JSON.stringify(result, null, 2)}
    </pre>
  );
}

export default ResultsView;

