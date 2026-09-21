# Frontend — Data Analysis Platform (MVP)

React + TypeScript SPA built with the **Next.js 14 App Router**, styled with **Tailwind
CSS** following `../ui_ux_design_system.md`, with **Plotly.js** for interactive charts.

It implements the 6 MVP screens: **login/register → upload → preview & clean → analyse →
charts → export**.

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
| `/` | Redirects to `/datasets` (signed in) or `/login` |
| `/login` | Ingia (login) |
| `/register` | Sajili (register, then auto-login) |
| `/datasets` | Dataset list with status badges, delete, links to every step |
| `/upload` | Drag & drop upload with a real progress bar |
| `/datasets/[id]` | Preview table, column profile, missing-value badges, cleaning actions + audit history |
| `/datasets/[id]/analyze` | Analysis type picker (descriptive stats / correlation / regression / hypothesis test), results + past analyses |
| `/datasets/[id]/charts` | Chart builder (bar/line/scatter/histogram) with live Plotly preview and saved charts |
| `/datasets/[id]/export` | Checklist of analyses + charts, PDF/XLSX choice, async status polling and download |

## 6. Structure

```
frontend/
├── app/
│   ├── layout.tsx              # fonts (Inter + IBM Plex Mono), ToastProvider
│   ├── globals.css             # Tailwind layers, skeleton shimmer, reduced-motion rules
│   ├── page.tsx                # /  -> /datasets or /login
│   ├── login/page.tsx  register/page.tsx
│   ├── upload/page.tsx
│   └── datasets/
│       ├── page.tsx
│       └── [id]/
│           ├── page.tsx        # preview + profile + cleaning
│           ├── analyze/page.tsx
│           ├── charts/page.tsx
│           └── export/page.tsx
├── components/
│   ├── AppShell.tsx            # sidebar nav + auth guard (desktop/mobile)
│   ├── Button.tsx Badge.tsx Card.tsx Skeleton.tsx DataTable.tsx Toast.tsx
│   ├── ChartView.tsx           # client-only Plotly wrapper (ssr: false)
│   ├── CleaningPanel.tsx       # cleaning actions + audit trail
│   └── ResultsView.tsx         # renders each analysis type
├── lib/
│   ├── api.ts                  # typed client for every endpoint (JWT from localStorage)
│   ├── constants.ts            # Okabe-Ito chart palette, semantic colours, spacing
│   └── useAuth.ts              # auth guard + logout
└── tailwind.config.ts          # design-system tokens (colours, type scale, fonts, radius)
```

## 7. Design-system notes (from `ui_ux_design_system.md`)

- Colours, type scale, 8px spacing scale and 8px radius live in `tailwind.config.ts`.
- Charts use the colourblind-safe **Okabe-Ito** palette from `lib/constants.ts`.
- Meaning is never colour-only: missing values / statuses use an icon **and** a colour.
- `Skeleton` shimmer is used while tables and charts load (instead of a bare spinner).
- Toasts slide in top-right and auto-dismiss after ~4s.
- `prefers-reduced-motion` disables decorative animation (`globals.css`).
- Touch targets on mobile are at least 44px (`min-h-[44px]` on nav/checkbox rows).
- Charts and tables carry `aria-label` / `caption` text for screen readers.
