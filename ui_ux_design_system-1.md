# UI/UX Design System — Data Analysis Platform

## 1. Falsafa ya design (Design philosophy)

- **Data-first:** UI haipaswi kushindana na data — rangi, mistari, na vipengele vya UI vinabaki neutral ili chati na namba ndizo zinazovutia jicho
- **Wazi na ya kuaminika (clean & trustworthy):** mfumo wa uchambuzi lazima uonekane mtaalamu — flat design, whitespace ya kutosha, si vitu vingi vya mapambo
- **Haraka kuhisi (perceived speed):** skeleton loaders, progress indicators, na micro-animations zinazofanya mtumiaji ahisi mfumo ni fast hata wakati wa big data processing
- **Rahisi kwa wote:** mtu asiye na ujuzi wa takwimu aelewe matokeo bila kusoma manual

---

## 2. Rangi (Color palette)

### Primary (Blue) — brand, vitufe vikuu, links
| Stop | Hex | Matumizi |
|---|---|---|
| 50 | #EFF6FF | Background nyepesi (hover states) |
| 100 | #DBEAFE | Badge/tag backgrounds |
| 300 | #93C5FD | Borders za accent |
| 500 | #3B82F6 | **Primary base** — icons, links |
| 600 | #2563EB | **Primary button bg** |
| 700 | #1D4ED8 | Button hover/active |
| 900 | #1E3A8A | Text juu ya background ya rangi |

### Neutral (Gray) — text, backgrounds, borders
| Stop | Hex | Matumizi |
|---|---|---|
| 50 | #F9FAFB | Page background |
| 100 | #F3F4F6 | Card/section background |
| 200 | #E5E7EB | Borders/dividers |
| 400 | #9CA3AF | Placeholder text |
| 600 | #4B5563 | Secondary text |
| 900 | #111827 | Primary text |

### Semantic (status)
| Jina | Rangi msingi | Background | Matumizi |
|---|---|---|---|
| Success | #16A34A | #F0FDF4 | Upload/analysis imekamilika |
| Warning | #D97706 | #FFFBEB | Missing values, tahadhari |
| Danger | #DC2626 | #FEF2F2 | Errors, kufuta data |
| Info | #0284C7 | #F0F9FF | Vidokezo/tooltips |

### Chart palette (colorblind-safe — Okabe-Ito)
Tumia rangi hizi 8 kwa michoro yenye makundi mengi (categorical data) — zinaonekana wazi hata kwa watu wenye color blindness:

`#0072B2` `#E69F00` `#009E73` `#CC79A7` `#56B4E9` `#D55E00` `#F0E442` `#999999`

**Kanuni:** kila category iwe na rangi ileile katika chati zote za dataset moja (usibadilishe rangi ya "Mkoa wa Dar" kati ya chati mbili).

### Dark mode
Badilisha tu tokens (si hardcoded hex kwenye components): `background` → gray-900, `surface` → gray-800, `text-primary` → gray-50, `border` → gray-700. Rangi za semantic na chart palette zinabaki zilezile (bado zinaonekana wazi juu ya background nyeusi).

---

## 3. Fonti (Typography)

- **UI font:** `Inter` (fallback: `-apple-system, "Segoe UI", sans-serif`) — inasomeka vizuri kwenye ukubwa mdogo, inafaa dashboards
- **Data/namba font:** `IBM Plex Mono` au `Roboto Mono` kwa **jedwali za namba na stats** — monospace inahakikisha namba zinapangana column kwa column (muhimu sana kwa data tables)

| Ngazi | Ukubwa | Uzito | Matumizi |
|---|---|---|---|
| Display | 32px | 600 | Page title kubwa (mfano dashboard header) |
| H1 | 28px | 600 | Kichwa cha ukurasa |
| H2 | 22px | 500 | Kichwa cha section |
| H3 | 18px | 500 | Kichwa cha card |
| Body-lg | 16px | 400 | Maelezo muhimu |
| Body | 14px | 400 | Maandishi ya kawaida |
| Caption | 12px | 400 | Labels, hints, timestamps |

Line-height: 1.5 kwa body text, 1.25 kwa headings.

---

## 4. Vitufe (Buttons)

| Aina | Mfano matumizi | Muonekano |
|---|---|---|
| Primary | "Pakia data", "Chambua" | Filled blue-600, weupe text |
| Secondary | "Ghairi", "Rudi nyuma" | Outline gray-300, text gray-700 |
| Ghost | Vitendo vidogo ndani ya jedwali | Bila border, hover bg gray-100 |
| Danger | "Futa dataset" | Filled red-600 |

**Sizes:** Small (32px height, 13px text) · Medium (40px, 14px) — default · Large (48px, 16px) — kwa main CTA kama "Anza uchambuzi"

**States:** default → hover (darken 10%) → active (scale 0.98) → disabled (opacity 40%, cursor not-allowed) → loading (spinner inline, text inabaki)

**Radius:** 8px kote. **Padding:** 12–20px horizontal kutegemea size.

---

## 5. Mwendo na animation (Motion)

| Aina | Muda | Easing | Matumizi |
|---|---|---|---|
| Micro (hover, button press) | 100–150ms | ease-out | Vitufe, icons |
| Standard transition | 200–250ms | ease-in-out | Kufungua/kufunga panel, tab switch |
| Page/route transition | 300ms | ease-out | Kuhama kati ya skrini |
| Chart entrance | 400–600ms | ease-out (staggered kwa bars) | Bar zikikua kutoka 0, line ikijichora |

**Micro-interactions muhimu:**
- **Upload:** progress bar yenye percentage halisi (si fake/indeterminate ukiwa na data ya kutosha kujua size)
- **Skeleton loaders** (si spinner peke yake) wakati jedwali/chati vinapakia — inatoa hisia ya speed
- **Toast notifications** zinazoingia kutoka juu-kulia, zinajiondoa baada ya sekunde 4
- **Hover kwenye chati:** tooltip inaonekana ndani ya 100ms ikionyesha thamani halisi
- Heshimu `prefers-reduced-motion` — zima animations za mapambo (si za kazi, kama progress bars) kwa watumiaji walioomba hivyo

---

## 6. Data visualization

**Uchaguzi wa chati kulingana na data:**
| Aina ya data | Chati inayopendekezwa |
|---|---|
| Kulinganisha makundi | Bar chart |
| Mwenendo kwa muda | Line chart |
| Uhusiano kati ya variable mbili | Scatter plot |
| Mgawanyo wa data (distribution) | Histogram |
| Sehemu ya jumla (proportions) | Donut/pie — *tumia kwa tahadhari, si zaidi ya makundi 5–6* |

**Kanuni za muundo:**
- Gridlines nyepesi (gray-200), si nzito — zisishindane na data
- Axis labels wazi, na units (%, TSh, kg, n.k.)
- Legend inaonekana tu ikiwa kuna makundi zaidi ya moja
- Tooltip kwenye hover ikionyesha thamani kamili (si iliyofupishwa)
- Empty state: "Hakuna data ya kutosha kuchora chati hii" badala ya chati tupu
- Error state: ujumbe wazi kama "Column hii sio ya namba, chagua nyingine"

---

## 7. Responsiveness

| Breakpoint | Upana | Muundo |
|---|---|---|
| Mobile | < 640px | Column moja, charts zinajipanga wima, jedwali kubwa zina horizontal scroll |
| Tablet | 640–1024px | Columns 2 pale inapofaa (mfano stats cards) |
| Desktop | > 1024px | Full dashboard na sidebar navigation + main content |

- **Touch targets:** angalau 44×44px kwenye mobile (vitufe, icons zinazobonyezwa)
- **Jedwali kwenye mobile:** badilisha kuwa "cards" (row moja = card moja) badala ya horizontal scroll ndefu inapowezekana
- **Charts kwenye mobile:** punguza idadi ya data points zinazoonyeshwa moja kwa moja (k.m. aggregate kwa wiki badala ya siku) ili chati isijazane

---

## 8. Spacing na grid

Msingi wa 8px: `4, 8, 12, 16, 24, 32, 48, 64px`. Tumia hizi tu — usiweke namba za ovyo kama 15px au 22px, inasaidia UI iwe consistent kote.

---

## 9. Icons

Tumia icon set moja tu (mfano Tabler Icons au Lucide) — outline style, ukubwa 20px (inline) / 24px (standalone buttons). Usichanganye icon sets tofauti.

---

## 10. Muundo wa taarifa kwenye skrini za matokeo (Progressive disclosure)

Skrini yoyote inayoonyesha matokeo ya uchambuzi (Matokeo ya Uchambuzi, Ripoti ya Utafiti, Dataset Profile) ifuate muundo huu wa tabaka 6 — kutoka rahisi kwenda undani — ili mtumiaji asiye na ujuzi wa takwimu aelewe haraka, huku yule mtaalamu akipata undani anaoutaka bila kuzuiwa:

1. **Kichwa cha habari (headline)** — sentensi moja ya lugha rahisi inayoeleza matokeo, pamoja na badge ya "umuhimu wa kitakwimu: ndiyo/hapana". Hii ndiyo kitu cha kwanza jicho linaloona.
2. **Namba muhimu (metric cards)** — r, p-value, n, method — kwenye cards fupi, si maandishi marefu
3. **Taswira (chart)** — huonyesha kile namba zinachosema kwa jicho
4. **Maelezo kamili** — yamefichwa nyuma ya "Angalia zaidi" (expandable/collapsible) — confidence interval, degrees of freedom, test statistic — kwa wale wanaotaka kuthibitisha kitaalamu
5. **Tafsiri kwa lugha rahisi** — aya fupi inayoeleza maana ya vitendo (practical meaning), si tu maana ya kitakwimu
6. **Hatua zinazofuata** — vitufe vya action (Pakua ripoti, Ongeza kwenye utafiti, Fanya uchambuzi mwingine)

**Kanuni ya msingi:** kama "piramidi iliyopinduliwa" ya habari — jibu kwanza, ushahidi baadaye. Usimlazimishe mtumiaji kusoma jedwali la namba kabla ya kujua jibu ni nini.

---

## 11. Accessibility

- Mkanganyiko wa rangi (contrast) angalau **4.5:1** kati ya text na background (WCAG AA)
- Vitufe vyote vinafikika kwa keyboard (Tab, Enter)
- Charts ziwe na `aria-label` inayoeleza kwa maneno kile chati inaonyesha (kwa screen readers)
- Usitegemee rangi peke yake kuonyesha maana — ongeza icon au pattern (mfano missing-value badge yenye icon ya tahadhari, si rangi nyekundu tu)
