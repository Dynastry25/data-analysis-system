/**
 * Translation tables.
 *
 * English is the source of truth: `en` defines the key set and `sw` is typed
 * against it, so adding a key without a Swahili translation is a compile error
 * rather than a silent fallback at runtime.
 *
 * These cover the shell and the dataset page. Pages added later should add their
 * keys here as they are translated — a partly translated app is normal, an
 * untranslated string that silently falls back to English is not.
 */
export const en = {
  // Shell and navigation
  "nav.dashboard": "Dashboard",
  "nav.dashboard.desc": "Summary of activity and the next step",
  "nav.projects": "Projects",
  "nav.projects.desc": "Organisations and the projects that involve you",
  "nav.data": "Data",
  "nav.data.desc": "Your datasets and file uploads",
  "nav.templates": "Templates",
  "nav.templates.desc": "Saved setups for common analyses",
  "nav.activity": "Activity",
  "nav.activity.desc": "Everything that has happened on your data",
  "nav.workspace": "Workspace",
  "nav.more": "Intelligence",
  "nav.profile": "Profile",
  "nav.profile.desc": "Your account and what you have done",
  "nav.settings": "Settings",
  "nav.settings.desc": "Appearance, data and account",
  "nav.help": "Help",
  "nav.help.desc": "How to use it and every method",
  "nav.admin": "Admin portal",
  "nav.skipToContent": "Skip to main content",

  // Common vocabulary
  "common.loading": "Loading",
  "common.retry": "Try again",
  "common.cancel": "Cancel",
  "common.save": "Save",
  "common.delete": "Delete",
  "common.close": "Close",
  "common.expand": "Expand",
  "common.collapse": "Collapse",
  "common.expandAll": "Expand all",
  "common.collapseAll": "Collapse all",
  "common.rows": "Rows",
  "common.columns": "Columns",
  "common.column": "Column",
  "common.name": "Name",
  "common.type": "Type",
  "common.version": "Version",
  "common.status": "Status",
  "common.uploaded": "Uploaded",
  "common.access": "Access",
  "common.private": "Private",
  "common.mean": "Mean",
  "common.median": "Median",
  "common.missing": "missing",
  "common.missingCells": "Missing cells",
  "common.totalCells": "Total cells",
  "common.uniqueValues": "Unique values",
  "common.min": "Lowest",
  "common.max": "Highest",
  "common.notAvailable": "—",
  "common.noResults": "Nothing to show yet",
  "common.valueMissing": "Value missing",
  "common.optional": "optional",
  "common.of": "of",

  // Language switcher
  "language.label": "Language",
  "language.switch": "Change language",
  "language.en": "English",
  "language.sw": "Kiswahili",
  "language.appliesTo":
    "Applies to the whole application and is remembered on this browser.",

  // Appearance
  "appearance.title": "Appearance",
  "appearance.description": "The application renders in light mode only.",
  "appearance.bodyOne":
    "StatFlow runs on a single theme: white and off-white, with navy text and blue accents.",
  "appearance.bodyTwo":
    "There is no theme switch because there is no second theme to choose. A control here would only look like it worked.",

  // Dataset page
  "dataset.backToList": "All datasets",
  "dataset.subtitle": "{version} \u00b7 Updated {relative}",
  "dataset.dataStudio": "Data studio",
  "dataset.assistant": "Assistant",
  "dataset.drawChart": "Draw chart",
  "dataset.runStatistics": "Run statistics",
  "dataset.meta.version": "Version",
  "dataset.meta.type": "Type",
  "dataset.meta.uploaded": "Uploaded",
  "dataset.meta.status": "Status",
  "dataset.meta.access": "Access",
  "dataset.error.title": "The dataset could not be loaded",
  "dataset.error.body": "Check the link and try again.",

  // Overview strip
  "overview.title": "Overview",
  "overview.version": "Version",
  "overview.type": "Type",
  "overview.uploaded": "Uploaded",
  "overview.status": "Status",
  "overview.access": "Access",
  // The section below the health verdict holds the preview and schema tables.
  // It needs its own heading: reusing overview.title printed "Overview" twice
  // on one page, once as the identity card and again above the tables.
  "overview.detail": "Detailed view",

  // Health
  "health.title": "Data health",
  "health.description":
    "Completeness, missing cells and a summary of the numeric columns. Computed by the engine, not estimated.",
  "health.needsCleaning": "Needs cleaning",
  "health.completeness": "Completeness",
  "health.missingCells": "Missing cells",
  "health.totalCells": "Total cells",
  "health.columnsWithGaps": "Columns with gaps",
  "health.columnsWithGapsOf": "{with} of {total}",
  "health.gapsByColumn": "Gaps by column",
  "health.numericSummary": "Numeric column summary",
  "health.allComplete": "Every column is full. No cell is missing.",
  "health.countWithZilizo": "{count} missing",
  "health.moreNumeric": "+{count} more numeric columns have a summary in the explore step.",
  "health.definitionOwn":
    "Completeness is the share of filled cells out of {total}. Treat that as your baseline before analysing.",
  "health.definitionShared":
    "This is another member's dataset, so your own results will inherit it.",
  "health.distributionAlt": "Distribution of {name}",

  // Health verdict
  "verdict.noGaps": "No gaps",
  "verdict.usable": "Usable",
  "verdict.needsCleaning": "Needs cleaning",
  "verdict.unusable": "Not usable yet",

  // Preview
  "preview.title": "Data preview",
  "preview.description":
    "The first {count} rows as they are now. Each column's type sits under its name.",
  "preview.footer": "{rows} rows · {columns} columns",
  "preview.empty.title": "No data to show",
  "preview.empty.description": "The file appears to have no rows.",
  "preview.moreHint":
    "Scroll the table sideways to reach every column, or open Explore for the full schema.",

  // Labels carried by the source file (Stata/SPSS)
  "labels.showLabel": "Show the labels from the file",
  "labels.showCode": "Show the numbers",
  "labels.hint":
    "{count} columns carry labels from the file. Use the switch on a column header to read its numbers instead.",
  "labels.badge": "Labelled",

  // Profiles
  "profiles.title": "Variable profiles",
  "profiles.description":
    "Type, centre and spread for every column. PASS means the column is complete and varies; WARN means there is something to look at.",
  "profiles.needReview": "{count} need review",
  "profiles.allClean": "All clean",
  "profiles.empty": "No columns yet.",
  "profiles.reasonMissing": "{count} cells missing",
  "profiles.reasonConstant": "a single value, it does not vary",
  "profiles.missingLabel": "missing",
  "profiles.note":
    "A mean is shown for numeric columns only. Categories have no mean — they are shown as the count of each group in the explore step.",
  "profiles.expandHint": "Open a column for its full distribution and category counts.",

  // Missing values warning
  "warning.title": "Warning: missing values",
  "warning.description":
    "The following columns have missing values. Clean them in the data studio before analysing so the results are sound.",
  "warning.clean": "Clean",
  "warning.columnCount": "{count} columns affected",

  // Schema table
  "schema.title": "Column structure",
  "schema.description": "Data type, missing values and unique values for every column.",
  "schema.expandHint": "Open a column below to see its distribution.",
  "schema.numeric": "Numeric",
  "schema.categorical": "Categorical",
  "schema.text": "Text",
  "schema.date": "Date",
  "schema.boolean": "Yes/No",

  // Variable and value labels declared by the source file
  "label.column": "Label",
  "label.none": "None",
  "label.codes": "Codes",
  "label.codedValues": "Coded values",
  "label.noLabel": "no label in the file",
  "label.moreCodes": "more codes",

  // Project and access
  "project.title": "Data access",
  "project.description":
    "Personal data stays yours. Once you put it in a project, the members of that organisation can see it according to their level.",
  "project.label": "Project",
  "project.personal": "Personal data",
  "project.assigned": "In a project",
  "project.personalBody":
    "This dataset is private. Only you can see it and run analyses on it.",
  "project.sharedBody":
    "This dataset belongs to a project, so organisation members can see it according to their level.",

  // Studio prompt
  "studio.title": "Clean and transform data",
  "studio.description": "The data studio creates a new version for each step, so no data is ever lost.",
  "studio.body":
    "Clean missing values, duplicates and column types, then transform (filter, group, calculate) before you analyse.",
  "studio.open": "Open data studio",

  // Relative time
  "time.now": "just now",
  "time.minutesAgo": "{count} min ago",
  "time.hoursAgo": "{count} hours ago",
  "time.daysAgo": "{count} days ago",
  "time.inMinutes": "in {count} min",
  "time.inHours": "in {count} hours",
  "time.inDays": "in {count} days",

  // ---- Shared components -------------------------------------------------
  // Copy that lives in reusable components rather than on a page. It is here
  // because a component cannot own its own dictionary: the same EmptyState is
  // used from ten pages, each of which would otherwise duplicate the string.
  "common.remove": "Remove",
  "common.open": "Open",
  "common.viewAll": "View all",
  "common.view": "View",
  "common.download": "Download",
  "common.edit": "Edit",
  "common.confirm": "Confirm",
  "common.back": "Back",
  "common.next": "Next",
  "common.previous": "Previous",
  "common.search": "Search",
  "common.filter": "Filter",
  "common.reset": "Reset",
  "common.showing": "Showing {shown} of {total}",
  "common.required": "required",
  "common.dash": "—",
  "common.unknown": "Unknown",
  "common.new": "New",
  "common.all": "All",
  "common.none": "None",

  "empty.title": "Nothing here yet",
  "empty.description": "There is nothing to show at the moment.",

  "action.upload": "Upload data",
  "action.pakia": "Upload",
  "action.open": "Open",
  "action.download": "Download",
  "action.view": "View",

  "status.draft": "Draft",
  "status.cleaned": "Cleaned",
  "status.analyzed": "Analyzed",
  "status.completed": "Completed",
  "status.failed": "Failed",
  "status.pending": "Pending",
  "status.inProgress": "In progress",

  // ---- Login and register ------------------------------------------------
  "auth.welcomeBack": "Welcome back",
  "auth.loginIntro": "Sign in to continue with your data analysis",
  "auth.email": "Email address",
  "auth.password": "Password",
  "auth.signIn": "Sign in",
  "auth.signingIn": "Signing in…",
  "auth.noAccount": "Don't have an account?",
  "auth.createOne": "Create one",
  "auth.forgot": "Forgot your password?",
  "auth.headline": "Analyse data without writing code",
  "auth.subheadline":
    "Six steps: upload, inspect, clean, analyse, chart, report. All in one system.",
  "auth.pointUploadTitle": "Upload quickly",
  "auth.pointAnalyseTitle": "Analyse step by step",
  "auth.pointAnalyseBody":
    "Complete statistics without writing code or asking an AI assistant.",
  "auth.pointReportTitle": "One-click reports",
  "auth.pointReportBody": "Generate a PDF or Excel file with all results and charts.",
  "auth.footer": "Secure system · your data is protected for every user",
  "auth.registerTitle": "Create your account",
  "auth.registerIntro": "Start analysing your data in minutes.",
  "auth.fullName": "Full name",
  "auth.confirmPassword": "Confirm password",
  "auth.passwordMismatch": "The passwords do not match.",
  "auth.createAccount": "Create account",
  "auth.haveAccount": "Already have an account?",
  "auth.signInInstead": "Sign in",
} as const;

export type TranslationKey = keyof typeof en;

export const sw: Record<TranslationKey, string> = {
  // Shell and navigation
  "nav.dashboard": "Dashboard",
  "nav.dashboard.desc": "Muhtasari wa shughuli na hatua inayofuata",
  "nav.projects": "Miradi",
  "nav.projects.desc": "Mashirika na miradi inayowahusu",
  "nav.data": "Data",
  "nav.data.desc": "Datasets zako na upakiaji wa faili",
  "nav.templates": "Makadirio",
  "nav.templates.desc": "Mipangilio ya kazi za kawaida za uchambuzi",
  "nav.activity": "Shughuli",
  "nav.activity.desc": "Kila kitu kilichofanyika kwenye data yako",
  "nav.workspace": "Eneo la kazi",
  "nav.more": "Uakalasimu",
  "nav.profile": "Wasifu",
  "nav.profile.desc": "Akaunti yako na kile umekikiri",
  "nav.settings": "Mipango",
  "nav.settings.desc": "Mwonekano, data na akaunti",
  "nav.help": "Msaada",
  "nav.help.desc": "Jinsi ya kutumia na mbinu zote",
  "nav.admin": "Lango la msimamizi",
  "nav.skipToContent": "Rukia hadi maudhui makuu",

  // Common vocabulary
  "common.loading": "Inapakia",
  "common.retry": "Jaribu tena",
  "common.cancel": "Ghairi",
  "common.save": "Hifadhi",
  "common.delete": "Futa",
  "common.close": "Funga",
  "common.expand": "Fungua",
  "common.collapse": "Funga",
  "common.expandAll": "Fungua zote",
  "common.collapseAll": "Funga zote",
  "common.rows": "Safu",
  "common.columns": "Columns",
  "common.column": "Column",
  "common.name": "Jina",
  "common.type": "Aina",
  "common.version": "Toleo",
  "common.status": "Hali",
  "common.uploaded": "Imepakiwa",
  "common.access": "Ufikiaji",
  "common.private": "Binafsi",
  "common.mean": "Wastani",
  "common.median": "Median",
  "common.missing": "zilizokosekana",
  "common.missingCells": "Cell zilizokosekana",
  "common.totalCells": "Cell zote",
  "common.uniqueValues": "Thamani unique",
  "common.min": "Chini kabisa",
  "common.max": "Juu kabisa",
  "common.notAvailable": "—",
  "common.noResults": "Hakuna kitu cha kuonyeshea bado",
  "common.valueMissing": "Thamani haipo",
  "common.optional": "si lazima",
  "common.of": "kati ya",

  // Language switcher
  "language.label": "Lugha",
  "language.switch": "Badilisha lugha",
  "language.en": "English",
  "language.sw": "Kiswahili",
  "language.appliesTo": "Inahusu programu nzima na hukumbukwa kwenye kivinjari hiki.",

  // Appearance
  "appearance.title": "Mwonekano",
  "appearance.description": "Programu inaonyesha kwa mandhari ya mchana pekee.",
  "appearance.bodyOne":
    "StatFlow inaendeshwa kwa mandhari moja tu: nyeupe na kijivu, yenye maandishi ya navy na maonyo ya buluu.",
  "appearance.bodyTwo":
    "Hakuna kitufe cha kubadilisha mandhari, kwa sabibu hakuna mandhari nyingine ya kuchagua. Kitufe hapa kisingewake kinaonekana tu kama inafanya kazi.",

  // Dataset page
  "dataset.backToList": "Datasets zote",
  "dataset.subtitle": "{version} \u00b7 Imebadilishwa {relative}",
  "dataset.dataStudio": "Data studio",
  "dataset.assistant": "Msaidizi",
  "dataset.drawChart": "Chora chati",
  "dataset.runStatistics": "Chambua takwimu",
  "dataset.meta.version": "Toleo",
  "dataset.meta.type": "Aina",
  "dataset.meta.uploaded": "Imepakiwa",
  "dataset.meta.status": "Hali",
  "dataset.meta.access": "Ufikiaji",
  "dataset.error.title": "Data haikuweza kupakiwa",
  "dataset.error.body": "Angalia kiungo kisha jaribu tena.",

  // Overview strip
  "overview.title": "Muhtasari",
  "overview.version": "Toleo",
  "overview.type": "Aina",
  "overview.uploaded": "Imepakiwa",
  "overview.status": "Hali",
  "overview.access": "Ufikiaji",
  "overview.detail": "Maelezo kamili",

  // Health
  "health.title": "Afya ya data",
  "health.description":
    "Kamilifu, cell zilizokosekana na muhtasari wa columns za nambari. Hesabiwa na engine, si kwa miongozo.",
  "health.needsCleaning": "Inahitaji kusafishwa",
  "health.completeness": "Kamilifu",
  "health.missingCells": "Cell zilizokosekana",
  "health.totalCells": "Cell zote",
  "health.columnsWithGaps": "Columns zilizo na mapengo",
  "health.columnsWithGapsOf": "{with} kati ya {total}",
  "health.gapsByColumn": "Mapengo kwa column",
  "health.numericSummary": "Muhtasari wa columns za nambari",
  "health.allComplete": "Kila column imejaa kabisa. Hakuna cell iliyokosekana.",
  "health.countWithZilizo": "{count} hazina",
  "health.moreNumeric": "+{count} columns zingine za nambari zina muhtasari kwenye hatua ya kuchunguza.",
  "health.definitionOwn":
    "Kamilifu ni sehemu zilizojaa za kati ya cell zote {total}. Fikilia kama hiyo ndiyo unayotaka kabla ya kuchambua.",
  "health.definitionShared":
    "Hii ni dataset ya mwanachama mwingine, hivyo matokeo yako yatamirika.",
  "health.distributionAlt": "Mgawanyo wa {name}",

  // Health verdict
  "verdict.noGaps": "Hakuna mapengo",
  "verdict.usable": "Inaweza kutumika",
  "verdict.needsCleaning": "Inahitaji kusafishwa",
  "verdict.unusable": "Hawezi kutumika bado",

  // Preview
  "preview.title": "Preview ya data",
  "preview.description":
    "Rows {count} za kwanza kama zilivyo sasa. Aina ya kila column iko chini ya jina lake.",
  "preview.footer": "{rows} rows · {columns} columns",
  "preview.empty.title": "Hakuna data ya kutosha",
  "preview.empty.description": "Faili linaonekana halina rows.",
  "preview.moreHint":
    "Sogeza meza kando ili kuona kila column, au fungua Uchunguzi kupata muundo kamili.",

  // Labels carried by the source file (Stata/SPSS)
  "labels.showLabel": "Onyesha majina yaliyo kwenye faili",
  "labels.showCode": "Onyesha nambari",
  "labels.hint":
    "Columns {count} zina majina yaliyo kwenye faili. Tumia kitufe kwenye kichwa cha column ili kuona nambari badala yake.",
  "labels.badge": "Imewekwa lebo",

  // Profiles
  "profiles.title": "Profiles za variables",
  "profiles.description":
    "Aina, wastani na mapengo kwa kila column. PASS inamaanisha kamba ina thamani zote na inabadilika; WARN inamaanisha kuna kitu cha kuangalia.",
  "profiles.needReview": "{count} zinahitaji kuangalia",
  "profiles.allClean": "Zote ziko safi",
  "profiles.empty": "Hakuna columns bado.",
  "profiles.reasonMissing": "{count} cell zilizokosekana",
  "profiles.reasonConstant": "thamani moja tu, haibadilishi",
  "profiles.missingLabel": "missing",
  "profiles.note":
    "Wastani linaonyeshwa kwa columns za nambari pekee. Kategoria hazina wastani — zinaonyeshwa kwa idadi ya kila kundi kwenye hatua ya kuchunguza.",
  "profiles.expandHint": "Fungua column ili kuona mgawanyo kamili na idadi ya kila kundi.",

  // Missing values warning
  "warning.title": "Tahadhari: missing values",
  "warning.description":
    "Columns zifuata zina thamani zilizo-kosekana. Safisha katika data studio kabla ya kuchambua ili matokeo yaweze sahihi.",
  "warning.clean": "Safisha",
  "warning.columnCount": "Columns {count} zimeathiriwa",

  // Schema table
  "schema.title": "Muundo wa columns",
  "schema.description": "Aina ya data, missing values na unique values kwa kila column.",
  "schema.expandHint": "Fungua column hapa chini ili kuona mgawanyo wake.",
  "schema.numeric": "Nambari",
  "schema.categorical": "Kategoria",
  "schema.text": "Maandishi",
  "schema.date": "Tarehe",
  "schema.boolean": "Ndiyo/Hapana",

  // Variable and value labels declared by the source file
  "label.column": "Lebo",
  "label.none": "Hakuna",
  "label.codes": "Msimbo",
  "label.codedValues": "Thamani zilizowekwa lebo",
  "label.noLabel": "hakuna lebo ndani ya faili",
  "label.moreCodes": "mimbo zaidi",

  // Project and access
  "project.title": "Ufikiaji wa data",
  "project.description":
    "Data ya binafsi ni yawewe pekee. Ukiiweka kwenye mradi, wanachama wa shirika hilo wataweza kuiona kulingana na kiwango chao.",
  "project.label": "Mradi",
  "project.personal": "Data ya binafsi",
  "project.assigned": "Kwenye mradi",
  "project.personalBody":
    "Dataset hii ni ya binafsi. Wewe pekee unaweza kuiona na kuchambua kwenye hiyo.",
  "project.sharedBody":
    "Dataset hii ni ya mradi, hivyo wanachama wa shirika wanaweza kuiona kulingana na kiwango chao.",

  // Studio prompt
  "studio.title": "Safisha na badilisha data",
  "studio.description": "Data studio huunda version mpya kwa kila hatua hakuna data inayopotea.",
  "studio.body":
    "Safisha missing values, duplicates na aina za columns, kisha badilisha (filter, group, calculate) kabla ya kuchambua.",
  "studio.open": "Fungua data studio",

  // Relative time
  "time.now": "sasa hivi",
  "time.minutesAgo": "kinyuma {count} min",
  "time.hoursAgo": "kinyuma {count} saa",
  "time.daysAgo": "kinyuma {count} siku",
  "time.inMinutes": "baada ya {count} min",
  "time.inHours": "baada ya {count} saa",
  "time.inDays": "baada ya {count} siku",

  // ---- Shared components -------------------------------------------------
  "common.remove": "Ondoa",
  "common.open": "Fungua",
  "common.viewAll": "Ona zote",
  "common.view": "Angalia",
  "common.download": "Pakua",
  "common.edit": "Hariri",
  "common.confirm": "Thibitisha",
  "common.back": "Rudi",
  "common.next": "Endelea",
  "common.previous": "Iliyotangulia",
  "common.search": "Tafuta",
  "common.filter": "Chuja",
  "common.reset": "Anza upya",
  "common.showing": "Inaonyesha {shown} kati ya {total}",
  "common.required": "inahitajika",
  "common.dash": "—",
  "common.unknown": "Haijulikani",
  "common.new": "Jipya",
  "common.all": "Zote",
  "common.none": "Hakuna",

  "empty.title": "Hakuna kitu hapa bado",
  "empty.description": "Hakuna kinachoweza kuonyeshwa kwa sasa.",

  "action.upload": "Pakia data",
  "action.pakia": "Pakia",
  "action.open": "Fungua",
  "action.download": "Pakua",
  "action.view": "Angalia",

  "status.draft": "Rasimu",
  "status.cleaned": "Imesafishwa",
  "status.analyzed": "Imechambuliwa",
  "status.completed": "Imekamilika",
  "status.failed": "Imeshindwa",
  "status.pending": "Inasubiri",
  "status.inProgress": "Inaendelea",

  // ---- Login and register ------------------------------------------------
  "auth.welcomeBack": "Karibu tena",
  "auth.loginIntro": "Ingia ili kuendelea na uchambuzi wa data yako",
  "auth.email": "Barua pepe (email)",
  "auth.password": "Nenosiri",
  "auth.signIn": "Ingia",
  "auth.signingIn": "Inaingia…",
  "auth.noAccount": "Huna akaunti?",
  "auth.createOne": "Tengeneza moja",
  "auth.forgot": "Umesahau nenosiri?",
  "auth.headline": "Chambua data bila kuandika code",
  "auth.subheadline":
    "Mtiririko wa hatua 6: pakia, angalia, safisha, chambua, buni chati, tengeneza ripoti. Yote katika mfumo mmoja.",
  "auth.pointUploadTitle": "Pakia kwa haraka",
  "auth.pointAnalyseTitle": "Chambua moja kwa moja",
  "auth.pointAnalyseBody":
    "Takwimu kamili bila kuandika code au uliza msaidizi wa AI.",
  "auth.pointReportTitle": "Ripoti ya kubonyeza moja",
  "auth.pointReportBody": "Tengeneza PDF au Excel yenye matokeo na chati zote.",
  "auth.footer": "Mfumo wenye usalama · data yako imelindwa kwa kila mtumiaji",
  "auth.registerTitle": "Tengeneza akaunti yako",
  "auth.registerIntro": "Anza kuchambua data yako kwa dakika chache.",
  "auth.fullName": "Jina kamili",
  "auth.confirmPassword": "Thibitisha nenosiri",
  "auth.passwordMismatch": "Manenosiri hayalingani.",
  "auth.createAccount": "Tengeneza akaunti",
  "auth.haveAccount": "Una akaunti tayari?",
  "auth.signInInstead": "Ingia",
};

export const dictionaries = { en, sw } as const;
