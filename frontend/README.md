# Frontend — Data Analysis Platform (MVP)

React + TypeScript SPA built with the **Next.js 14 App Router**, styled with **Tailwind
CSS** following `../ui_ux_design_system.md`, with **Plotly.js** for interactive charts.

It implements the StatFlow pipeline — **login/register → upload → validate → profile →
clean → transform → explore → analyse → charts → explain → report → export** — grouped
into the six phases the product is organised around (**Data → Prepare → Analyze →
Visualize → Explain → Report**), with a **dashboard home** that surfaces the platform's
features, quick actions and a stage-by-stage workflow guide.

---

## 1. Setup

```powershell
cd D:\Project\Data-Analysis-system\frontend
npm install
```

## 2. Run (dev)

```powershell
cd D:\Project\Data-Analysis-system\frontend
npm run dev
```

Open `http://localhost:3000`. The backend must be running on `http://localhost:8000`
(see `../backend/README.md`).

## 3. Production build

```powershell
cd D:\Project\Data-Analysis-system\frontend
npm run build
npm run start
```

## 4. Environment

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/api` | Base URL of the FastAPI backend |

Create `.env.local` to override it:

```
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

## 5. Routes

| Route | Screen |
|---|---|
| `/` | Redirects to `/dashboard` (signed in) or `/login` |
| `/dashboard` | **Home**: greeting, overview metrics, quick actions, recent datasets with per-dataset progress, 6-stage workflow guide |
| `/login` | Ingia (login, split-screen brand panel) |
| `/register` | Sajili (register, then auto-login) |
| `/datasets` | Dataset list with metric cards, status badges, stage progress, links to every step |
| `/upload` | Drag & drop upload with a real progress bar |
| `/datasets/[id]` | Summary metric cards, **`ProfileSummary`** visuals (completeness, type split, unique per column, missing per column), column profile table, preview table, access/project control, Data Studio link |
| `/datasets/[id]/studio` | Versioned cleaning + transforms, operation history, version preview/download |
| `/datasets/[id]/statistics` | Unified statistics studio (all engine analyses + versioned run history) |
| `/datasets/[id]/analyze` | Redirects to `/statistics` (kept so old links keep working) |
| `/datasets/[id]/ask` | AI statistical assistant (natural-language questions, verified results) |
| `/datasets/[id]/charts` | Chart builder (bar/line/scatter/histogram) with live Plotly preview and saved charts |
| `/datasets/[id]/export` | Checklist of analyses + charts, PDF/XLSX choice, async status polling and download |
| `/organizations` | Mashirika: list + create (creator becomes **owner**) |
| `/organizations/[id]` | Org detail: RBAC member management (owner/admin/analyst/viewer roles), projects CRUD |

### The workflow (`lib/pipeline.ts`)

The whole product shares **one workflow definition** — `lib/pipeline.ts` is the single
source of truth. It holds two levels:

- **11 stages**, the real work: Pakia `/upload` · Thibitisha `/datasets/[id]/validate` ·
  Profile `/datasets/[id]/studio?stage=profile` · Safisha `…/studio?stage=clean` ·
  Badilisha `…/studio?stage=transform` · Chunguza `/datasets/[id]/explore` ·
  Uchambuzi `/datasets/[id]/statistics` · Chora `/datasets/[id]/charts` ·
  Eleza `/datasets/[id]/ask` · Ripoti `/datasets/[id]/export?stage=report` ·
  Hamisha `…/export?stage=export`.
- **6 phases**, the compact layer the design asks for: Data · Prepare · Analyze ·
  Visualize · Explain · Report. Eleven items do not fit in a bar on a laptop, so the
  phases are what a returning user navigates by, and `hrefForPhase()` is the one
  function that answers "where does phase X start for dataset Y".

It drives four surfaces so the user always knows where they are in the flow:

- **Sidebar** — Dashboard, Projects, Data, then the five phase links. Phase links act
  on the dataset in the URL, else on the most recent one.
- **`WorkflowStrip`** — the `DATA → PREPARE → … → REPORT` bar under the top bar, on
  every screen, with the phase you are in highlighted.
- **`JourneyRail`** — the evidence layer inside a dataset page: all 11 stages, each
  marked done only when a stored record proves it.
- **Datasets list + Dashboard** — a `Hatua x/11`-style progress indicator and a
  "Mtiririko wa kazi" guide of clickable stage cards for new users.

## 6. Structure

```
frontend/
├── app/
│   ├── layout.tsx              # fonts (Inter + IBM Plex Mono), ToastProvider
│   ├── globals.css             # Tailwind layers, skeleton shimmer, reduced-motion rules
│   ├── page.tsx                # /  -> /dashboard or /login
│   ├── login/page.tsx  register/page.tsx
│   ├── dashboard/page.tsx      # home: metrics, quick actions, recent datasets, pipeline guide
│   ├── upload/page.tsx
│   └── datasets/
│       ├── page.tsx
│       └── [id]/
│           ├── page.tsx        # preview + profile + Data Studio link
│           ├── analyze/page.tsx  # redirect -> statistics (legacy route kept alive)
│           ├── statistics/page.tsx  # unified statistics studio
│           ├── studio/page.tsx   # versioned cleaning + transforms
│           ├── ask/page.tsx      # AI assistant chat
│           ├── charts/page.tsx
│           └── export/page.tsx
├── components/
│   ├── AppShell.tsx            # sidebar (nav + phases) → TopBar → WorkflowStrip → page
│   ├── TopBar.tsx              # search, help (from pipeline.ts), activity, user menu
│   ├── WorkflowStrip.tsx       # DATA → PREPARE → … → REPORT bar, on every screen
│   ├── Icon.tsx                # single inline SVG icon set (Lucide-style, no dependency)
│   ├── MetricCard.tsx          # overview metric with icon badge
│   ├── ProfileSummary.tsx      # profile drawn: completeness, types, unique, missing
│   ├── QuickActions.tsx        # shortcut cards to the main features
│   ├── Button.tsx Badge.tsx Card.tsx Skeleton.tsx DataTable.tsx Toast.tsx
│   ├── ChartView.tsx           # client-only Plotly wrapper (ssr: false)
│   └── StandardResultView.tsx  # renders every unified standard result
├── lib/
│   ├── api.ts                  # typed client for every endpoint (JWT from localStorage)
│   ├── constants.ts            # Okabe-Ito chart palette, semantic colours, spacing
│   ├── pipeline.ts             # THE 6-stage workflow: labels, routes, progress mapping
│   └── useAuth.ts              # auth guard + logout
└── tailwind.config.ts          # design-system tokens (colours, type scale, fonts, radius)
```

## 7. Design-system notes (from `ui_ux_design_system.md`)

- Colours, type scale, 8px spacing scale and 8px radius live in `tailwind.config.ts`.
- One icon set (`components/Icon.tsx`, Lucide-style outline SVGs) — no third-party
  icon dependency, so builds stay offline-safe (design system §9).
- The shell is four zones, top to bottom: a dark **sidebar** (brand, Dashboard /
  Projects / Data, then the five workflow phases, plus the admin link for platform
  admins), a **top bar** (search, help, activity, account), the **workflow strip**,
  then the page. On mobile the sidebar is an off-canvas drawer opened from the top bar.
- The reference mock for this layout draws its chrome at 8–10px type with ~30px rows,
  which contradicts this project's own design system (§3 caption 12px, §11 44px touch
  targets and 4.5:1 contrast). So the **arrangement** follows the mock and the
  **sizing** follows the design system.
- The top bar's panels are backed by real endpoints (dataset search, recent activity);
  nothing in it is a placeholder that looks like a feature.
- Charts use the colourblind-safe **Okabe-Ito** palette from `lib/constants.ts`.
- Meaning is never colour-only: missing values / statuses use an icon **and** a colour.
- `Skeleton` shimmer is used while tables and charts load (instead of a bare spinner).
- Toasts slide in top-right and auto-dismiss after ~4s.
- `prefers-reduced-motion` disables decorative animation (`globals.css`).
- Touch targets on mobile are at least 44px (`min-h-[44px]` on nav/checkbox rows).
- Charts and tables carry `aria-label` / `caption` text for screen readers.
