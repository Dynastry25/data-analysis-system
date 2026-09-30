# STATFLOW — UI/UX & Product Design Specification

**Document type:** UI/UX Design System + Product Flow Specification  
**Product:** StatFlow — AI-Powered Data Analysis Platform  
**Design direction:** Premium, modern, data-focused SaaS  
**Primary workflow:** Data → Prepare → Analyze → Visualize → Explain → Report

---

## 1. Purpose

This document defines how the StatFlow product should **look, behave, and flow** from the user's first login through data upload, preparation, statistical analysis, visualization, AI explanation, reporting, collaboration, and administration.

The UI must feel like a real production-grade analytics application rather than a generic admin dashboard. The visual language should be professional enough for statisticians, researchers, students, businesses, NGOs, government institutions, analysts, and data scientists while remaining approachable to beginners.

The product architecture requires a clear separation between the AI layer and the trusted statistical engine. The AI creates a structured plan, validation happens before execution, the statistical engine calculates the result, and AI explains the verified result.

---

# 2. Product Experience Principles

## 2.1 Core principles

1. **Data first** — the dataset is always visible and traceable.
2. **Clarity over decoration** — visual polish must never hide analytical information.
3. **Progressive disclosure** — beginners see simple controls first; advanced options are available when needed.
4. **Reproducibility** — every transformation and analysis should show dataset version, method, variables, configuration, timestamp, and user.
5. **Trust** — computed values must be visually distinguished from AI interpretation.
6. **Speed** — the UI should remain responsive for large datasets and background jobs.
7. **Consistency** — the same buttons, cards, tables, badges, forms, charts, and navigation patterns should be reused everywhere.
8. **Accessibility** — keyboard navigation, readable contrast, visible focus states, semantic controls, and clear error messages are required.
9. **Responsive design** — desktop is the primary analytical experience; tablet and mobile should provide usable monitoring, review, and management experiences.
10. **Professional analytics aesthetic** — avoid excessive gradients, oversized illustrations, marketing-style sections, and unnecessary decoration.

---

# 3. Global Visual Direction

## 3.1 Design concept

The primary visual direction is:

- Premium SaaS
- Modern analytics workspace
- Dark navy navigation
- Light analytics canvas
- Electric indigo/blue primary accent
- Subtle cyan secondary accent
- White and very-light neutral surfaces
- Thin borders
- Soft shadows
- Medium-radius corners
- Dense but readable information
- Minimal glass effects, used only for elevated/high-priority surfaces

The UI should communicate:

> **Powerful enough for professional statistics, simple enough for everyday users.**

---

# 4. Color System

Use CSS variables/design tokens so the entire application can be themed consistently.

## 4.1 Primary palette

| Token | Suggested value | Usage |
|---|---|---|
| `--color-primary-950` | `#0B1020` | Deep navigation/background |
| `--color-primary-900` | `#111827` | Sidebar / dark surfaces |
| `--color-primary-800` | `#172554` | Dark active areas |
| `--color-primary-700` | `#1D4ED8` | Strong primary actions |
| `--color-primary-600` | `#2563EB` | Primary buttons |
| `--color-primary-500` | `#4F46E5` | Main indigo accent |
| `--color-primary-400` | `#6366F1` | Hover/highlight |
| `--color-cyan-500` | `#06B6D4` | Secondary analytics accent |

## 4.2 Neutral palette

| Token | Suggested value | Usage |
|---|---|---|
| `--color-white` | `#FFFFFF` | Cards / surfaces |
| `--color-slate-50` | `#F8FAFC` | Application background |
| `--color-slate-100` | `#F1F5F9` | Input/background |
| `--color-slate-200` | `#E2E8F0` | Borders |
| `--color-slate-300` | `#CBD5E1` | Disabled/secondary borders |
| `--color-slate-500` | `#64748B` | Secondary text |
| `--color-slate-700` | `#334155` | Body text |
| `--color-slate-900` | `#0F172A` | Headings |

## 4.3 Semantic colors

Use semantic colors consistently:

- **Success:** `#16A34A`
- **Warning:** `#F59E0B`
- **Error:** `#DC2626`
- **Info:** `#0284C7`
- **AI:** use the primary indigo/cyan family rather than a separate rainbow palette.

Semantic colors must communicate state, not decorate the interface.

---

# 5. Typography

## 5.1 Primary font

Recommended:

**Inter**

Fallback:

`system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`

Inter should be used for:

- navigation
- buttons
- headings
- tables
- forms
- dashboard labels
- chart labels
- statistical results

## 5.2 Type scale

| Element | Size | Weight |
|---|---:|---:|
| Page title | 28–32px | 700 |
| Section title | 20–24px | 650–700 |
| Card title | 15–18px | 600 |
| Body | 14–15px | 400 |
| Secondary text | 12–13px | 400–500 |
| Button | 13–14px | 600 |
| Table text | 13–14px | 400–500 |
| KPI value | 24–32px | 700 |
| Micro label | 11–12px | 600 |

Avoid using too many font sizes on a single screen.

---

# 6. Spacing, Radius and Elevation

## 6.1 Spacing

Use a consistent 4px/8px-based spacing system:

- 4px — micro spacing
- 8px — icon/text spacing
- 12px — compact controls
- 16px — normal component spacing
- 24px — card padding
- 32px — section spacing
- 40–48px — major layout separation

## 6.2 Border radius

Recommended:

- Inputs: 8px
- Buttons: 8px
- Cards: 12–16px
- Large workspace panels: 16px
- Modal: 16px
- Pills/badges: 999px

## 6.3 Shadows

Use subtle shadows only:

- `shadow-sm` for normal cards
- `shadow-md` for floating menus/modals
- stronger shadows only for drag-and-drop overlays or critical dialogs

The interface should rely more on spacing and borders than heavy shadows.

---

# 7. Global Application Layout

The main authenticated application should use:

```text
┌─────────────────────────────────────────────────────────────┐
│ Top Bar: Project / Dataset / Version / Search / AI / User  │
├───────────────┬─────────────────────────────────────────────┤
│               │                                             │
│ Dark Sidebar  │                Main Workspace              │
│               │                                             │
│ Dashboard     │                                             │
│ Projects      │                                             │
│ Datasets      │                                             │
│ Prepare       │                                             │
│ Analyze       │                                             │
│ Visualize     │                                             │
│ Dashboards    │                                             │
│ Reports       │                                             │
│ AI Assistant  │                                             │
│               │                                             │
│ Team          │                                             │
│ Settings      │                                             │
│ Help          │                                             │
└───────────────┴─────────────────────────────────────────────┘
```

## 7.1 Sidebar

The sidebar should contain:

### Main

- Dashboard
- Projects
- Datasets
- Data Preparation
- Analysis
- Visualizations
- Dashboards
- Reports
- AI Assistant

### Workspace

- Recent
- Favorites
- Shared with me

### Administration/Account

- Team
- Billing
- Settings
- Help

The active navigation item should use:

- subtle indigo background
- clear icon
- white/bright text
- left accent indicator

The sidebar should support a collapsed mode.

---

# 8. Top Navigation

The top bar should include:

- current project
- current dataset
- dataset version
- global search
- command/search shortcut
- notifications
- AI Assistant shortcut
- user avatar/menu

For analysis workspaces also show:

- Save
- Undo
- Redo
- Run
- Export
- Share

Buttons should become icon-only at smaller widths where appropriate.

---

# 9. Buttons

## 9.1 Primary button

Use for the main action:

- Upload Dataset
- Run Analysis
- Create Project
- Generate Report
- Save Changes

Style:

- indigo/blue fill
- white text
- 8px radius
- medium weight
- subtle hover darkening
- visible keyboard focus

## 9.2 Secondary button

Use for supporting actions:

- Cancel
- Preview
- Configure
- Duplicate
- View Details

Style:

- white/light background
- thin border
- dark text

## 9.3 Ghost button

Use for low-emphasis actions:

- Undo
- Redo
- Refresh
- More
- Close

## 9.4 Destructive button

Use only for destructive actions:

- Delete Dataset
- Delete Project
- Remove Member

Use confirmation dialogs for destructive actions.

---

# 10. Cards

Cards are the main information container.

## Card types

### KPI Card

Contains:

- metric name
- current value
- change
- optional sparkline
- optional status

Example:

```text
Datasets
128
+12.4%
Last 30 days
```

### Analysis Result Card

Contains:

- method
- variables
- sample size
- main statistic
- p-value
- confidence interval
- status
- View Full Result

### Data Quality Card

Contains:

- missing %
- duplicate count
- invalid values
- outliers
- quality score

### AI Insight Card

Contains:

- AI icon
- short verified insight
- source/result reference
- Explain
- View Analysis

### Activity Card

Contains:

- user
- action
- dataset/project
- timestamp
- status

---

# 11. Status Badges

Use consistent compact badges.

Examples:

- `READY`
- `PROCESSING`
- `COMPLETED`
- `FAILED`
- `DRAFT`
- `SHARED`
- `PRIVATE`
- `ARCHIVED`

Statistical assumption badges:

- `PASS`
- `WARN`
- `FAIL`

Do not rely on color alone. Include text and/or icons.

---

# 12. Main User Flow

The product's main journey is:

```text
LOGIN
  ↓
DASHBOARD
  ↓
CREATE PROJECT
  ↓
UPLOAD DATASET
  ↓
VALIDATE
  ↓
PREVIEW
  ↓
PROFILE
  ↓
PREPARE
  ↓
CREATE DATASET VERSION
  ↓
EXPLORE
  ↓
ANALYZE
  ↓
CHECK ASSUMPTIONS
  ↓
VERIFY RESULT
  ↓
VISUALIZE
  ↓
AI EXPLANATION
  ↓
DASHBOARD / REPORT
  ↓
EXPORT / SHARE
```

The workflow indicator should appear inside relevant workspaces:

**Data → Prepare → Analyze → Visualize → Explain → Report**

Current stage is highlighted; completed stages remain clickable where allowed.

---

# 13. Screen-by-Screen UI Specification

# 13.1 Welcome / Login

## Layout

Two-column desktop layout:

### Left

- StatFlow logo
- product statement
- short value proposition
- subtle analytics visualization

### Right

Login card:

- Email
- Password
- Remember me
- Forgot password
- Sign in
- Continue with supported provider
- Create account

Keep the screen premium and minimal.

---

# 13.2 Main Dashboard

Dashboard should immediately answer:

- What have I been working on?
- What datasets are available?
- What analyses are running?
- What needs attention?
- How can I start quickly?

## Top

Greeting + project selector + quick action.

## KPI row

- Projects
- Datasets
- Analyses
- Storage
- AI usage

## Main content

### Recent Projects

Card/table list.

### Recent Datasets

Show:

- name
- rows
- columns
- size
- quality score
- last updated

### Analysis Activity

Timeline/list.

### Quick Actions

- Upload Dataset
- New Project
- Run Analysis
- Ask StatFlow AI
- Create Dashboard
- Generate Report

---

# 13.3 Projects & Datasets

Use a hybrid list/grid.

## Project card

- project name
- description
- datasets count
- analysis count
- last activity
- owner
- collaborators
- menu

## Dataset table

Columns:

- Dataset
- Rows
- Columns
- Size
- Quality
- Version
- Updated
- Owner
- Actions

Features:

- search
- filters
- sorting
- pagination
- bulk selection
- archive
- delete
- share

---

# 13.4 Dataset Explorer

This is one of the most important screens.

## Header

```text
Dataset Name
v4 • 125,430 rows • 32 columns

[Prepare] [Analyze] [Visualize] [Ask AI]
```

## Main tabs

- Overview
- Data
- Variables
- Profile
- Versions
- Operations

## Data table

Must support:

- sticky header
- column resizing
- column sorting
- filtering
- search
- type indicators
- null indicators
- pagination/virtualization
- row selection

Variable type icons:

- Numeric
- Categorical
- Date
- Boolean
- Text
- ID

---

# 13.5 Data Quality / Profiling

Show a quality overview at the top.

Example:

```text
Data Quality
92 / 100

Missing values     2.1%
Duplicates         43
Outliers           1.8%
Invalid values     0.3%
```

## Profile cards

For each variable:

- type
- missing
- unique
- min
- max
- mean
- median
- SD
- distribution preview
- top categories where applicable

Highlight problems:

- missing data
- duplicates
- invalid types
- extreme values
- suspicious categories

Every warning should provide a suggested action.

---

# 13.6 Data Preparation Studio

Use a three-panel workspace.

```text
LEFT                 CENTER                    RIGHT
Variables            Data preview             Operation
Filters              Preview results          Configuration
Transformations      Before/after             Parameters
```

## Operations

- Remove duplicates
- Fill missing
- Rename columns
- Change data type
- Select columns
- Drop columns
- Filter rows
- Sort
- Create calculated column
- Group-by aggregation

## Important UX requirement

Every operation must produce a visible operation history:

```text
1. Removed duplicates
2. Filled missing income with median
3. Converted age → integer
4. Created income_per_acre
```

Allow:

- Undo
- Redo
- Edit
- Delete operation
- Reorder where safe
- Save as new version

---

# 13.7 Statistical Analysis Studio

The screen should make statistical analysis understandable without hiding advanced options.

## Layout

### Left

Analysis categories:

- Descriptive
- Frequency
- Correlation
- Comparison
- Association
- ANOVA
- Regression
- Advanced
- Future ML
- Survey Analysis

### Center

Analysis configuration.

Example:

```text
Analysis
Pearson Correlation

Variable X
[Income]

Variable Y
[Farm Size]

Confidence Level
[95%]

[Run Analysis]
```

### Right

Method recommendation / assumptions.

Example:

```text
Recommended Method

Pearson Correlation

Why?
Both selected variables are numeric.

Assumptions
PASS Normality
PASS Linear relationship
WARN Outliers
```

The system should explain method selection.

---

# 13.8 Analysis Result Studio

The result screen should prioritize the statistical answer.

## Header

```text
Pearson Correlation
Income × Farm Size

n = 350
```

## Main result

Large value:

```text
r = 0.61
p < 0.001
95% CI [0.54, 0.67]
```

## Sections

- Summary
- Assumptions
- Statistics
- Effect size
- Confidence interval
- Interpretation
- Visualization
- Methodology
- Reproducibility
- Export

## Reproducibility panel

Show:

- Dataset
- Version
- Variables
- Filters
- Transformations
- Method
- Configuration
- User
- Timestamp
- StatFlow version

---

# 13.9 AI Statistical Copilot

The AI must look like a professional analytical copilot, not a generic chatbot.

## Layout

### Left

Conversation/history.

### Center

AI question and verified response.

### Right

Context:

- Dataset
- Variables
- Analysis
- Method
- Assumptions
- Result source

## Response structure

Every statistical AI response should be organized into:

1. Question
2. Understanding
3. Variables Used
4. Method Selected
5. Why This Method
6. Assumptions
7. Data Quality
8. Sample Size
9. Statistical Result
10. Effect Size
11. Confidence Interval
12. P-value
13. Interpretation
14. Limitations
15. Suggested Next Analysis
16. Charts

## Critical trust indicator

Clearly label:

**Computed by Statistical Engine**

and separately:

**AI Interpretation**

The AI must never fabricate statistical values.

---

# 13.10 Visualization Studio

The visualization builder should be highly interactive.

## Chart configuration

Users select:

- X axis
- Y axis
- Color
- Size
- Facet
- Aggregation
- Filter
- Sort
- Annotation

## Supported chart families

At minimum:

- Bar
- Column
- Line
- Area
- Scatter
- Histogram
- Box plot
- Pie/donut
- Heatmap
- Frequency chart
- Correlation visualization

Future-ready:

- Maps
- Choropleth maps
- Statistical plots
- Survey visualizations

## Chart toolbar

- Edit
- Filter
- Zoom
- Fullscreen
- Download
- Duplicate
- Add to Dashboard
- Add to Report
- View Data

Exports:

- PNG
- SVG
- PDF

---

# 13.11 Dashboard Builder

Dashboard builder should use drag-and-drop.

## Widget types

- KPI
- Chart
- Table
- Statistic
- Text
- Filter
- Map
- AI Insight

## Layout

```text
Toolbar
-----------------------------------
Grid workspace

[ KPI ] [ KPI ] [ KPI ] [ KPI ]

[      Main chart      ] [Table]

[     Trend chart      ] [Insight]
```

Features:

- drag
- resize
- duplicate
- delete
- configure
- save
- preview
- share
- export

Dashboard filters should update connected widgets.

---

# 13.12 Reports

Report builder should provide a document-like experience.

## Report structure

1. Title
2. Dataset information
3. Data quality
4. Methodology
5. Descriptive statistics
6. Statistical analysis
7. Charts
8. Interpretation
9. Conclusion
10. Limitations
11. Appendix

## Controls

- Add section
- Reorder
- Edit
- Add chart
- Add table
- Add result
- Add AI explanation
- Preview
- Export

Formats:

- PDF
- DOCX
- PPTX
- HTML
- Excel where applicable

---

# 14. Research Mode

Create a specialized research workflow.

## Research workspace

```text
Research Question
Objectives
Hypotheses
Variables
Data
Analysis
Results
Tables
Charts
Interpretation
Report
```

Features:

- research questions
- objectives
- hypotheses
- conceptual framework
- descriptive statistics
- inferential statistics
- regression
- publication-style tables
- APA-style output where appropriate

Never generate invented research results.

---

# 15. Survey Analysis

The UI should be ready for survey datasets.

Features:

- weights
- strata
- clusters
- sampling units
- Likert scales
- reliability analysis
- Cronbach's alpha
- index construction
- weighted frequencies

Advanced survey configuration should appear only when the user activates Survey Mode.

---

# 16. Large Dataset UX

The UI must not attempt to load the entire dataset into browser memory.

For large datasets:

```text
Upload
 ↓
Validation
 ↓
Object Storage
 ↓
Parquet
 ↓
Polars / DuckDB
 ↓
Background Job
 ↓
Result Cache
 ↓
Frontend
```

The UI must show job states:

- Queued
- Processing
- Completed
- Failed

For long operations show:

- progress
- current task
- estimated stage
- cancel where safe
- notification when completed

Tables should use:

- pagination
- virtualized rendering
- server-side filtering where appropriate

---

# 17. Collaboration

Project collaboration UI should support:

- invite member
- roles
- comments
- review
- shared dashboard
- shared report
- activity history

Permission levels should be visible but not clutter the workspace.

Suggested role presentation:

- Owner
- Editor
- Analyst
- Viewer

All permissions must be enforced server-side.

---

# 18. Notifications

Notification center should include:

- analysis completed
- dataset processing completed
- report generated
- invitation received
- project shared
- job failed
- storage warning
- AI usage warning
- subscription event

Use grouped notifications and clear read/unread states.

---

# 19. Search / Command Palette

Add a global command palette.

Shortcut:

`Ctrl/Cmd + K`

Users can search:

- projects
- datasets
- variables
- analyses
- reports
- dashboards
- settings

Actions can include:

- Upload Dataset
- Create Project
- Run Analysis
- Ask AI
- Create Dashboard
- Generate Report

---

# 20. Empty States

Every module needs a useful empty state.

Do not show:

> No data.

Instead show:

```text
No datasets yet

Upload your first CSV, XLSX, JSON or Parquet file
to start exploring your data.

[Upload Dataset]
```

Empty states should always provide the next action.

---

# 21. Loading States

Use skeleton loaders for:

- cards
- tables
- charts
- profile panels
- analysis results

For long operations use progress states rather than indefinite spinners.

---

# 22. Error States

Errors must be understandable.

Example:

```text
Analysis could not be completed

The selected variables contain insufficient valid observations.

What you can do:
• Check missing values
• Review filters
• Select another variable

[Review Data] [Change Analysis]
```

Never expose backend stack traces.

---

# 23. Confirmation Modals

Use confirmations for:

- delete dataset
- delete project
- delete report
- remove team member
- permanently delete version
- destructive transformations

For irreversible actions, clearly state consequences.

---

# 24. Visualization Design Rules

Charts must prioritize:

1. readable labels
2. correct statistical representation
3. clear titles
4. meaningful units
5. accessible contrast
6. useful tooltips
7. data source/version visibility

Every chart should support:

- title
- subtitle/description where useful
- legend when required
- tooltip
- export
- data table
- fullscreen

Avoid decorative 3D charts and misleading visual effects.

---

# 25. Admin Portal

The admin portal must feel like a **platform operations center**, not a copy of the user dashboard.

Use a slightly denser interface while preserving the same StatFlow design system.

## Admin navigation

### Overview

- Admin Dashboard
- System Health
- Activity

### Platform

- Users
- Organizations
- Projects
- Datasets
- Analyses
- Jobs
- Reports

### AI & Usage

- AI Usage
- AI Requests
- Model/feature usage
- Usage limits
- Feature Flags

### Business

- Plans
- Subscriptions
- Billing
- Revenue
- Entitlements

### Security

- Audit Logs
- Access Control
- Security Events
- API Keys
- Sessions

### System

- Storage
- Background Jobs
- API Health
- Errors
- Integrations
- System Settings

---

# 26. Admin Dashboard

## Top KPI row

- Total Users
- Active Users
- Organizations
- Datasets
- Analyses
- AI Requests
- Storage
- Errors

## Main charts

### User growth

Line chart.

### Platform activity

Line/bar chart.

### Dataset volume

Trend chart.

### AI usage

Usage trend.

### System jobs

Queued / processing / completed / failed.

## Right-side alerts

- high error rate
- failed jobs
- storage threshold
- unusual activity
- subscription events

---

# 27. User Management

Admin user table:

| User | Organization | Role | Status | Last Active | Created | Actions |
|---|---|---|---|---|---|---|

Actions:

- View
- Edit
- Suspend
- Reactivate
- Reset access
- View activity
- View usage

User detail page should contain:

- profile
- organization
- roles
- datasets
- projects
- usage
- activity
- security events

---

# 28. Organization Management

Organization page:

- organization name
- owner
- members
- plan
- storage
- datasets
- analyses
- AI usage
- billing status
- created date

Actions:

- View
- Edit
- Change plan
- Suspend
- Delete according to policy

---

# 29. Dataset Administration

Admin dataset table:

- Dataset
- Owner
- Organization
- Size
- Rows
- Columns
- Version
- Status
- Created
- Last activity

Admin should be able to investigate operational problems without bypassing normal authorization/audit rules.

---

# 30. Job Monitoring

Create a dedicated operations screen.

Columns:

- Job ID
- Type
- User
- Dataset
- Status
- Progress
- Started
- Duration
- Worker
- Actions

Filters:

- queued
- processing
- completed
- failed
- cancelled

Job detail should show:

- parameters
- logs summary
- timestamps
- error code
- retry option where safe

---

# 31. System Health

Use a monitoring-style layout.

## Services

```text
API              HEALTHY
Database         HEALTHY
Storage          HEALTHY
Statistical      HEALTHY
AI Service       HEALTHY
Job Queue        HEALTHY
```

Use semantic badges.

## Metrics

- response time
- request rate
- error rate
- queue length
- storage
- database health

---

# 32. Audit Logs

Audit log should be highly searchable.

Columns:

- timestamp
- user
- organization
- action
- resource
- resource ID
- IP where appropriate
- result
- metadata

Filters:

- date
- user
- organization
- action
- resource
- status

Audit entries should be immutable from the normal admin UI.

---

# 33. Billing & Plans Admin

Plans:

- FREE
- STUDENT
- PRO
- TEAM
- ENTERPRISE

Show configurable entitlements:

- storage
- dataset size
- analyses
- AI requests
- exports
- team members

The UI should clearly distinguish:

**Plan configuration**

from

**Customer subscription**

Billing rules must be controlled by the backend, not by frontend logic.

---

# 34. AI Administration

AI admin screen should show:

- total AI requests
- requests by organization
- requests by feature
- successful requests
- failed requests
- average processing time
- usage limits
- model/feature configuration

AI logs should be treated as sensitive operational data and protected accordingly.

---

# 35. Feature Flags

Admin can control controlled rollouts.

Example:

```text
Advanced Regression       ON
Survey Analysis           ON
Research Mode             ON
Geospatial                OFF
ML Module                 OFF
New AI Copilot            ON
```

Each flag should include:

- name
- description
- environment
- status
- rollout scope
- last changed
- changed by

---

# 36. Admin Settings

Organize settings into sections:

### General

- platform name
- logo
- timezone
- default language

### Security

- session policy
- password policy
- MFA settings
- login controls

### Storage

- limits
- retention
- cleanup policy

### AI

- usage limits
- feature access
- safety configuration

### Email

- provider
- notifications
- templates

### Integrations

- storage
- payment
- authentication
- external APIs

---

# 37. Admin Roles

Minimum roles:

## Super Admin

Can manage:

- platform
- admins
- users
- organizations
- billing
- security
- feature flags
- system settings

## Platform Admin

Can manage:

- users
- organizations
- datasets
- jobs
- reports
- usage
- support operations

## Support/Admin Viewer

Read-focused access to:

- users
- organizations
- jobs
- audit logs
- system status

Permissions must be enforced server-side.

---

# 38. Mobile UX

Desktop is the primary analysis environment.

Mobile should prioritize:

- dashboard monitoring
- project browsing
- dataset summaries
- analysis result review
- AI assistant
- notifications
- reports
- admin monitoring

Complex data preparation and dashboard construction can use a simplified responsive experience.

Never force large statistical tables into an unusable mobile layout.

---

# 39. Accessibility

Required:

- keyboard navigation
- visible focus states
- semantic buttons
- accessible labels
- sufficient contrast
- non-color status indicators
- readable tables
- accessible dialogs
- keyboard-accessible dropdowns
- screen-reader-friendly icons

---

# 40. Responsive Breakpoints

Recommended:

```text
Mobile:   < 640px
Tablet:   640–1023px
Desktop:  1024–1439px
Large:    1440px+
```

Desktop analytical workspace should make strong use of available horizontal space without becoming excessively wide.

---

# 41. Component Library

Create reusable components rather than styling individual screens independently.

Required core components:

```text
Button
IconButton
Input
Select
MultiSelect
Checkbox
Radio
Switch
Tabs
Badge
Tooltip
Dropdown
Modal
Drawer
Toast
Alert
Card
StatCard
DataTable
DataGrid
Pagination
SearchBar
FilterBar
DatePicker
FileUploader
ProgressBar
Skeleton
EmptyState
ErrorState
ChartCard
ChartToolbar
AnalysisResult
AssumptionBadge
AIInsight
ActivityTimeline
UserAvatar
CommandPalette
```

Every reusable component should have a consistent API and state behavior.

---

# 42. Data Table Design

The DataTable is a core StatFlow component.

Features:

- sticky header
- sorting
- filtering
- column visibility
- column resizing
- search
- pagination
- virtualization
- row selection
- export
- density control
- fullscreen

Numeric values should be aligned consistently.

Dates should use consistent formatting.

Missing values should have a subtle but recognizable representation.

---

# 43. Statistical Tables

Statistical tables must be more formal than ordinary application tables.

Support:

- variable names
- N
- mean
- SD
- median
- minimum
- maximum
- statistic
- df
- p-value
- effect size
- confidence interval

For research output, support publication-style formatting where appropriate.

---

# 44. AI Trust UX

The AI interface must visually distinguish:

### System-computed

> Calculated by StatFlow Statistical Engine

### AI-generated explanation

> Explanation generated from the verified statistical result

### User configuration

> Analysis parameters selected by the user

This separation is essential for user trust.

---

# 45. Reproducibility UX

Every analysis result should have:

**Reproduce Analysis**

Clicking it opens the original configuration:

```text
Dataset
Version
Variables
Filters
Transformations
Method
Parameters
Assumptions
```

User can:

- rerun
- duplicate
- modify
- save as new analysis

---

# 46. Versioning UX

Dataset versions should be visible:

```text
v1 Original
v2 Removed duplicates
v3 Filled missing values
v4 Added calculated variable
```

Each version should show:

- created by
- timestamp
- parent version
- operations
- row count
- column count

Never silently overwrite important dataset states.

---

# 47. Export UX

Export dialog:

```text
Export

Format
[PDF ▼]

Include
☑ Summary
☑ Tables
☑ Charts
☑ Methodology
☑ Interpretation
☐ Appendix

[Cancel] [Generate Export]
```

For long exports show a background-job state.

---

# 48. Global UX States

Every feature should have these states designed before implementation:

1. Default
2. Hover
3. Focus
4. Active
5. Disabled
6. Loading
7. Empty
8. Success
9. Warning
10. Error
11. Processing
12. Completed

---

# 49. Visual Hierarchy Rules

A page should have:

1. One clear primary heading.
2. One dominant primary action.
3. Clear section grouping.
4. Strong whitespace.
5. Consistent alignment.
6. Predictable navigation.
7. Minimal competing colors.

Do not turn every card into a colored card.

---

# 50. Recommended Screen Inventory

## User application

1. Welcome
2. Login
3. Register
4. Dashboard
5. Projects
6. Project Detail
7. Dataset Upload
8. Upload Validation
9. Dataset Explorer
10. Data Profile
11. Data Preparation
12. Dataset Versions
13. Analysis Studio
14. Analysis Recommendation
15. Assumption Checks
16. Analysis Results
17. Reproducibility
18. AI Statistical Copilot
19. Visualization Studio
20. Dashboard Builder
21. Dashboard Viewer
22. Reports
23. Report Builder
24. Research Mode
25. Survey Analysis
26. Collaboration
27. Notifications
28. Billing
29. Settings
30. Help

## Admin application

31. Admin Login
32. Admin Dashboard
33. Users
34. User Detail
35. Organizations
36. Organization Detail
37. Datasets
38. Analyses
39. Jobs
40. Job Detail
41. System Health
42. Audit Logs
43. AI Usage
44. Feature Flags
45. Plans
46. Subscriptions
47. Billing
48. Storage
49. Security
50. Admin Settings

---

# 51. Navigation Logic

The user's primary navigation should follow the natural analytical lifecycle:

```text
Dashboard
   ↓
Projects
   ↓
Datasets
   ↓
Prepare
   ↓
Analyze
   ↓
Visualize
   ↓
Dashboards
   ↓
Reports
```

AI should remain globally available because it can assist at multiple stages.

---

# 52. UX for Method Recommendation

When the user selects variables, StatFlow should display:

```text
Recommended Analysis

Independent Samples t-test

Why this method?
• Outcome is numeric
• Grouping variable is categorical
• Two groups detected

Assumptions

Normality       PASS
Independence    PASS
Equal variance  WARN

Alternative
Mann–Whitney U

[Use Recommended Method]
[Configure Manually]
```

The UI should explain recommendations instead of simply selecting a method invisibly.

---

# 53. UX for Analysis Failure

If an analysis cannot run:

```text
Unable to run analysis

Reason
There are not enough valid observations after filtering.

Affected variables
Income
Farm Size

Suggested actions
• Review missing values
• Remove restrictive filters
• Select another method

[Review Data]
[Change Analysis]
```

---

# 54. UX for Long-Running Analysis

```text
Running Regression

Preparing data          ✓
Checking assumptions    ✓
Running model           ●
Generating results      ○
Generating charts       ○

Progress 62%

You can continue working. We will notify you when the result is ready.
```

---

# 55. Final Design Quality Standard

The finished StatFlow UI should feel like a combination of:

- professional statistics software
- modern BI platform
- premium SaaS workspace
- AI analytical copilot

But it must maintain its own identity.

The most important visual characteristics are:

- premium
- clean
- trustworthy
- data-dense but readable
- fast
- structured
- consistent
- accessible
- professional

Avoid:

- excessive gradients
- giant decorative illustrations
- random colors
- oversized cards
- unnecessary glassmorphism
- generic chatbot UI
- dashboard clutter
- inconsistent buttons
- inconsistent spacing
- charts without context
- unexplained statistical results

---

# 56. Implementation Acceptance Checklist

The UI/UX implementation should not be considered complete until:

- [ ] All primary pages exist.
- [ ] All primary navigation flows work.
- [ ] Dataset upload flow is clear.
- [ ] Dataset validation state is visible.
- [ ] Dataset preview works.
- [ ] Profiling is understandable.
- [ ] Data preparation has operation history.
- [ ] Dataset versioning is visible.
- [ ] Statistical method recommendation is understandable.
- [ ] Assumption checks are visible.
- [ ] Analysis results are structured.
- [ ] AI results clearly separate computation from explanation.
- [ ] Visualizations are interactive.
- [ ] Dashboards support configurable widgets.
- [ ] Reports support configurable sections.
- [ ] Reproducibility information is accessible.
- [ ] Collaboration controls are understandable.
- [ ] Large-data jobs have visible progress states.
- [ ] Empty/loading/error/success states are designed.
- [ ] Admin dashboard is separate and operationally focused.
- [ ] Admin users, organizations, datasets, jobs and audit logs are manageable.
- [ ] AI usage can be monitored.
- [ ] Billing and plans are manageable.
- [ ] Feature flags exist.
- [ ] Security settings exist.
- [ ] Responsive behavior is defined.
- [ ] Accessibility states are implemented.
- [ ] Design tokens are centralized.
- [ ] Reusable components are used consistently.

---

# 57. Design-to-Code Rule

The prototype should be treated as the **visual reference**, while this document is the **implementation specification**.

Developers should reproduce:

- layout hierarchy
- spacing
- navigation behavior
- typography
- colors
- cards
- buttons
- tables
- charts
- badges
- modals
- AI interaction patterns
- dashboard behavior
- admin structure

The final implementation should use reusable components and design tokens rather than copying styles independently into every page.

---

# 58. Product Architecture UX Principle

StatFlow's most important product flow is:

```text
USER QUESTION
      ↓
DATASET SCHEMA
      ↓
VARIABLE MAPPING
      ↓
METHOD RECOMMENDATION
      ↓
VALIDATION
      ↓
STATISTICAL ENGINE
      ↓
VERIFIED RESULT
      ↓
AI EXPLANATION
      ↓
CHART / TABLE
      ↓
REPORT
```

The AI should **not** directly calculate statistical values.

The statistical engine remains the source of truth for numerical calculations.

---

# 59. Final Product Experience

A user should be able to open StatFlow and understand within seconds:

**What data do I have?**

**What can I do with it?**

**What is wrong with my data?**

**Which analysis should I use?**

**What does the result mean?**

**Can I visualize it?**

**Can I reproduce it?**

**Can I put it in a report?**

**Can I share it?**

The interface should make these answers obvious without forcing the user to learn the entire system before becoming productive.

---

## Source Alignment

This specification preserves the core StatFlow workflow and terminology from the supplied project specification, including:

- dataset upload and validation
- preview and profiling
- cleaning and transformation
- immutable dataset versions
- operation history
- statistical analysis
- assumption checks
- method recommendation
- visualization
- dashboards
- reports
- AI Statistical Assistant
- collaboration
- security and RBAC
- audit logs
- billing
- administration
- large-dataset/background-job architecture
- reproducibility
- Research Mode
- Survey Analysis
- future ML and geospatial capabilities

The visual system and detailed component behavior in this document are the UI/UX design layer intended to turn those product capabilities into a coherent production interface.
