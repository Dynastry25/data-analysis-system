# Frontend — Data Analysis Platform (MVP)

React + TypeScript SPA built with the **Next.js 14 App Router**, styled with **Tailwind
CSS** following `../ui_ux_design_system.md`, with **Plotly.js** for interactive charts.

It implements the 6-step StatFlow pipeline — **login/register → upload → preview →
clean → analyse → charts → export** — with a **dashboard home** that surfaces the
platform's features, quick actions and a stage-by-stage workflow guide.

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
| `/datasets/[id]` | Preview table, column profile, missing-value badges, link card to Data Studio |
| `/datasets/[id]/studio` | Versioned cleaning + transforms, operation history, version preview/download |
| `/datasets/[id]/statistics` | Unified statistics studio (all engine analyses + versioned run history) |
| `/datasets/[id]/analyze` | Redirects to `/statistics` (kept so old links keep working) |
| `/datasets/[id]/ask` | AI statistical assistant (natural-language questions, verified results) |
| `/datasets/[id]/charts` | Chart builder (bar/line/scatter/histogram) with live Plotly preview and saved charts |
| `/datasets/[id]/export` | Checklist of analyses + charts, PDF/XLSX choice, async status polling and download |

### The 6-stage pipeline (`lib/pipeline.ts`)

The whole product shares **one workflow definition** — `lib/pipeline.ts` is the single
source of truth:

1. **Pakia** `/upload`
2. **Angalia** `/datasets/[id]`
3. **Safisha** `/datasets/[id]/studio`
4. **Chambua** `/datasets/[id]/statistics`
5. **Chati** `/datasets/[id]/charts`
6. **Ripoti** `/datasets/[id]/export`

It drives four surfaces so the user always knows where they are in the flow:

- **Sidebar "Mtiririko" section** on every dataset page (compact numbered steps).
- **`PipelineStepper`** — horizontal stepper above the content on dataset pages;
  completed stages show a check, the current one is filled, all are clickable.
- **Datasets list + Dashboard** show a `Hatua x/6`-style progress indicator each.
- **Dashboard "Mtiririko wa kazi" guide** — clickable stage cards for new users.

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
│   ├── AppShell.tsx            # brand + grouped sidebar, mobile drawer, pipeline stepper
│   ├── Icon.tsx                # single inline SVG icon set (Lucide-style, no dependency)
│   ├── PipelineStepper.tsx     # horizontal 6-stage workflow stepper
│   ├── MetricCard.tsx          # overview metric with icon badge
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
- The sidebar has three zones: primary nav, the 6-stage **Mtiririko** flow (only on
  dataset pages), and the signed-in user + logout at the bottom. On mobile it is an
  off-canvas drawer.
- Charts use the colourblind-safe **Okabe-Ito** palette from `lib/constants.ts`.
- Meaning is never colour-only: missing values / statuses use an icon **and** a colour.
- `Skeleton` shimmer is used while tables and charts load (instead of a bare spinner).
- Toasts slide in top-right and auto-dismiss after ~4s.
- `prefers-reduced-motion` disables decorative animation (`globals.css`).
- Touch targets on mobile are at least 44px (`min-h-[44px]` on nav/checkbox rows).
- Charts and tables carry `aria-label` / `caption` text for screen readers.
