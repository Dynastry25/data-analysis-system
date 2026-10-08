"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { createPortal } from "react-dom";

import { Icon } from "./Icon";
import { useLanguage } from "@/lib/i18n";
import { api, DatasetSummary, ProjectSummary } from "@/lib/api";

interface CommandItem {
  id: string;
  label: string;
  description: string;
  icon: string;
  category: string;
  action: () => void;
  keywords: string[];
}

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  datasets: DatasetSummary[];
}

function filterItems(items: CommandItem[], query: string): CommandItem[] {
  if (!query.trim()) return items;
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  return items.filter((item) => {
    const searchText = [
      item.label.toLowerCase(),
      item.description.toLowerCase(),
      item.category.toLowerCase(),
      ...item.keywords.map((k) => k.toLowerCase()),
    ].join(" ");
    return terms.every((term) => searchText.includes(term));
  });
}

function categorizeItems(items: CommandItem[]): Record<string, CommandItem[]> {
  const categories: Record<string, CommandItem[]> = {};
  for (const item of items) {
    if (!categories[item.category]) {
      categories[item.category] = [];
    }
    categories[item.category].push(item);
  }
  return categories;
}

export function CommandPalette({ isOpen, onClose, datasets }: CommandPaletteProps) {
  const { t } = useLanguage();
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [items, setItems] = useState<CommandItem[]>([]);
  const [initialized, setInitialized] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setQuery("");
      setSelectedIndex(0);
      if (inputRef.current) {
        inputRef.current.focus();
      }
    }
  }, [isOpen]);

  useEffect(() => {
    if (!initialized) {
      const staticItems: CommandItem[] = [
        // Navigation
        {
          id: "nav-dashboard",
          label: t("nav.dashboard"),
          description: t("nav.dashboard.desc"),
          icon: "dashboard",
          category: t("cmd.category.navigation"),
          action: () => window.location.href = "/dashboard",
          keywords: ["home", "overview", "dash"],
        },
        {
          id: "nav-projects",
          label: t("nav.projects"),
          description: t("nav.projects.desc"),
          icon: "folder",
          category: t("cmd.category.navigation"),
          action: () => window.location.href = "/organizations",
          keywords: ["projects", "org", "organization", "workspace"],
        },
        {
          id: "nav-data",
          label: t("nav.data"),
          description: t("nav.data.desc"),
          icon: "database",
          category: t("cmd.category.navigation"),
          action: () => window.location.href = "/datasets",
          keywords: ["datasets", "data", "upload"],
        },
        {
          id: "nav-templates",
          label: t("nav.templates"),
          description: t("nav.templates.desc"),
          icon: "clipboard",
          category: t("cmd.category.navigation"),
          action: () => window.location.href = "/templates",
          keywords: ["templates", "template"],
        },
        {
          id: "nav-activity",
          label: t("nav.activity"),
          description: t("nav.activity.desc"),
          icon: "history",
          category: t("cmd.category.navigation"),
          action: () => window.location.href = "/activity",
          keywords: ["activity", "history", "recent"],
        },
        {
          id: "nav-profile",
          label: t("nav.profile"),
          description: t("nav.profile.desc"),
          icon: "user",
          category: t("cmd.category.navigation"),
          action: () => window.location.href = "/profile",
          keywords: ["profile", "account", "settings"],
        },
        {
          id: "nav-settings",
          label: t("nav.settings"),
          description: t("nav.settings.desc"),
          icon: "sliders",
          category: t("cmd.category.navigation"),
          action: () => window.location.href = "/settings",
          keywords: ["settings", "preferences", "config"],
        },
        {
          id: "nav-help",
          label: t("nav.help"),
          description: t("nav.help.desc"),
          icon: "info",
          category: t("cmd.category.navigation"),
          action: () => window.location.href = "/help",
          keywords: ["help", "docs", "documentation", "guide"],
        },

        // Create actions
        {
          id: "create-dataset",
          label: t("cmd.create.dataset"),
          description: t("cmd.create.dataset.desc"),
          icon: "upload",
          category: t("cmd.category.create"),
          action: () => window.location.href = "/upload",
          keywords: ["new", "upload", "import", "csv", "excel"],
        },
        {
          id: "create-project",
          label: t("cmd.create.project"),
          description: t("cmd.create.project.desc"),
          icon: "folder",
          category: t("cmd.category.create"),
          action: () => window.location.href = "/organizations",
          keywords: ["new", "project", "workspace", "org"],
        },
        {
          id: "create-analysis",
          label: t("cmd.create.analysis"),
          description: t("cmd.create.analysis.desc"),
          icon: "calculator",
          category: t("cmd.category.create"),
          action: () => {
            const latest = datasets[0];
            if (latest) window.location.href = `/datasets/${latest.id}/statistics`;
          },
          keywords: ["new", "analysis", "statistics", "test", "model"],
        },
        {
          id: "create-chart",
          label: t("cmd.create.chart"),
          description: t("cmd.create.chart.desc"),
          icon: "chart",
          category: t("cmd.category.create"),
          action: () => {
            const latest = datasets[0];
            if (latest) window.location.href = `/datasets/${latest.id}/charts`;
          },
          keywords: ["new", "chart", "visualize", "plot", "graph"],
        },
        {
          id: "create-dashboard",
          label: t("cmd.create.dashboard"),
          description: t("cmd.create.dashboard.desc"),
          icon: "dashboard",
          category: t("cmd.category.create"),
          action: () => {
            const latest = datasets[0];
            if (latest) window.location.href = `/datasets/${latest.id}/dashboard`;
          },
          keywords: ["new", "dashboard", "widget", "kpi"],
        },
        {
          id: "create-report",
          label: t("cmd.create.report"),
          description: t("cmd.create.report.desc"),
          icon: "file-text",
          category: t("cmd.category.create"),
          action: () => {
            const latest = datasets[0];
            if (latest) window.location.href = `/datasets/${latest.id}/export`;
          },
          keywords: ["new", "report", "export", "pdf", "docx", "pptx"],
        },

        // Analysis types (quick access)
        {
          id: "analysis-descriptive",
          label: t("cmd.analysis.descriptive"),
          description: t("cmd.analysis.descriptive.desc"),
          icon: "table",
          category: t("cmd.category.analysis"),
          action: () => {
            const latest = datasets[0];
            if (latest) window.location.href = `/datasets/${latest.id}/statistics?type=descriptive`;
          },
          keywords: ["descriptive", "summary", "mean", "median", "stats"],
        },
        {
          id: "analysis-regression",
          label: t("cmd.analysis.regression"),
          description: t("cmd.analysis.regression.desc"),
          icon: "trending-up",
          category: t("cmd.category.analysis"),
          action: () => {
            const latest = datasets[0];
            if (latest) window.location.href = `/datasets/${latest.id}/statistics?type=linear_regression`;
          },
          keywords: ["regression", "linear", "predict", "model"],
        },
        {
          id: "analysis-classification",
          label: t("cmd.analysis.classification"),
          description: t("cmd.analysis.classification.desc"),
          icon: "target",
          category: t("cmd.category.analysis"),
          action: () => {
            const latest = datasets[0];
            if (latest) window.location.href = `/datasets/${latest.id}/statistics?type=logistic_regression_classification`;
          },
          keywords: ["classification", "logistic", "binary", "ml", "machine learning"],
        },
        {
          id: "analysis-clustering",
          label: t("cmd.analysis.clustering"),
          description: t("cmd.analysis.clustering.desc"),
          icon: "layers",
          category: t("cmd.category.analysis"),
          action: () => {
            const latest = datasets[0];
            if (latest) window.location.href = `/datasets/${latest.id}/statistics?type=kmeans`;
          },
          keywords: ["clustering", "kmeans", "group", "segment", "unsupervised"],
        },
        {
          id: "analysis-pca",
          label: t("cmd.analysis.pca"),
          description: t("cmd.analysis.pca.desc"),
          icon: "layers",
          category: t("cmd.category.analysis"),
          action: () => {
            const latest = datasets[0];
            if (latest) window.location.href = `/datasets/${latest.id}/statistics?type=pca`;
          },
          keywords: ["pca", "dimensionality", "reduction", "components"],
        },
        {
          id: "analysis-survey",
          label: t("cmd.analysis.survey"),
          description: t("cmd.analysis.survey.desc"),
          icon: "clipboard",
          category: t("cmd.category.analysis"),
          action: () => {
            const latest = datasets[0];
            if (latest) window.location.href = `/datasets/${latest.id}/statistics?type=likert_analysis`;
          },
          keywords: ["survey", "likert", "cronbach", "weighted", "questionnaire"],
        },

        // Workflow phases
        {
          id: "phase-prepare",
          label: t("cmd.phase.prepare"),
          description: t("cmd.phase.prepare.desc"),
          icon: "sliders",
          category: t("cmd.category.workflow"),
          action: () => {
            const latest = datasets[0];
            if (latest) window.location.href = `/datasets/${latest.id}/prepare`;
          },
          keywords: ["prepare", "clean", "transform", "wrangle"],
        },
        {
          id: "phase-analyze",
          label: t("cmd.phase.analyze"),
          description: t("cmd.phase.analyze.desc"),
          icon: "calculator",
          category: t("cmd.category.workflow"),
          action: () => {
            const latest = datasets[0];
            if (latest) window.location.href = `/datasets/${latest.id}/statistics`;
          },
          keywords: ["analyze", "statistics", "test", "hypothesis"],
        },
        {
          id: "phase-visualize",
          label: t("cmd.phase.visualize"),
          description: t("cmd.phase.visualize.desc"),
          icon: "chart",
          category: t("cmd.category.workflow"),
          action: () => {
            const latest = datasets[0];
            if (latest) window.location.href = `/datasets/${latest.id}/charts`;
          },
          keywords: ["visualize", "chart", "plot", "graph", "viz"],
        },
        {
          id: "phase-explain",
          label: t("cmd.phase.explain"),
          description: t("cmd.phase.explain.desc"),
          icon: "sparkles",
          category: t("cmd.category.workflow"),
          action: () => {
            const latest = datasets[0];
            if (latest) window.location.href = `/datasets/${latest.id}/assistant`;
          },
          keywords: ["explain", "assistant", "ai", "interpret", "narrative"],
        },
        {
          id: "phase-report",
          label: t("cmd.phase.report"),
          description: t("cmd.phase.report.desc"),
          icon: "file-text",
          category: t("cmd.category.workflow"),
          action: () => {
            const latest = datasets[0];
            if (latest) window.location.href = `/datasets/${latest.id}/export`;
          },
          keywords: ["report", "export", "pdf", "docx", "pptx", "html"],
        },

        // Settings & utilities
        {
          id: "util-keyboard",
          label: t("cmd.util.keyboard"),
          description: t("cmd.util.keyboard.desc"),
          icon: "sliders",
          category: t("cmd.category.utilities"),
          action: () => window.location.href = "/help#keyboard-shortcuts",
          keywords: ["shortcuts", "hotkeys", "keys", "keyboard"],
        },
        {
          id: "util-theme",
          label: t("cmd.util.theme"),
          description: t("cmd.util.theme.desc"),
          icon: "shield",
          category: t("cmd.category.utilities"),
          action: () => window.location.href = "/settings#appearance",
          keywords: ["theme", "dark", "light", "appearance"],
        },
        {
          id: "util-language",
          label: t("cmd.util.language"),
          description: t("cmd.util.language.desc"),
          icon: "globe",
          category: t("cmd.category.utilities"),
          action: () => window.location.href = "/settings#language",
          keywords: ["language", "locale", "translation", "swahili", "english"],
        },
      ];

      // Add dataset-specific items
      for (const ds of datasets) {
        staticItems.push({
          id: `dataset-${ds.id}`,
          label: `${ds.original_filename}`,
          description: `Dataset #${ds.id} · v${ds.current_version} · ${ds.rows} rows`,
          icon: "database",
          category: t("cmd.category.datasets"),
          action: () => window.location.href = `/datasets/${ds.id}`,
          keywords: ["dataset", "data", ds.original_filename.toLowerCase()],
        });
      }

      setItems(staticItems);
      setInitialized(true);
    }
  }, [initialized, datasets, t]);

  const filteredItems = filterItems(items, query);
  const categorized = categorizeItems(filteredItems);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (!isOpen) return;

      if (event.key === "Escape") {
        onClose();
        return;
      }

      if (event.key === "ArrowDown") {
        event.preventDefault();
        setSelectedIndex((prev) => Math.min(prev + 1, filteredItems.length - 1));
        return;
      }

      if (event.key === "ArrowUp") {
        event.preventDefault();
        setSelectedIndex((prev) => Math.max(prev - 1, 0));
        return;
      }

      if (event.key === "Enter" && filteredItems[selectedIndex]) {
        event.preventDefault();
        filteredItems[selectedIndex].action();
        onClose();
        return;
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, filteredItems, selectedIndex, onClose]);

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 lg:pt-24">
      <div
        className="fixed inset-0 bg-black/50"
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="relative w-full max-w-2xl bg-surface-panel rounded-[12px] border border-surface-border shadow-card overflow-hidden">
        <div className="relative">
          <div className="absolute inset-y-0 left-0 flex items-center pl-4 pointer-events-none text-ink-muted">
            <Icon name="search" size={20} />
          </div>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") onClose();
            }}
            placeholder={t("cmd.placeholder")}
            className="w-full h-14 pl-12 pr-4 text-body text-ink bg-transparent border-none focus-visible:outline-none placeholder:text-ink-muted"
            autoFocus
            aria-label={t("cmd.placeholder")}
          />
          <kbd className="absolute right-4 top-1/2 -translate-y-1/2 px-2 py-1 text-[10px] font-mono text-ink-muted bg-surface-sunken rounded">
            {typeof navigator !== "undefined" && navigator.platform.includes("Mac") ? "⌘K" : "Ctrl+K"}
          </kbd>
        </div>

        <div className="max-h-[50vh] overflow-y-auto">
          {filteredItems.length === 0 ? (
            <div className="p-8 text-center text-ink-muted">
              <Icon name="search" size={32} className="mx-auto mb-2 opacity-50" />
              <p className="text-body">{t("cmd.noResults")}</p>
              <p className="text-caption mt-1">{t("cmd.noResultsHint")}</p>
            </div>
          ) : (
            <>
              {Object.entries(categorized).map(([category, catItems]) => (
                <div key={category} className="border-t border-surface-border">
                  <div className="px-4 py-2 text-overline uppercase tracking-wide text-ink-muted bg-surface-sunken">
                    {category}
                  </div>
                  {catItems.map((item, index) => {
                    const globalIndex = filteredItems.indexOf(item);
                    const isSelected = globalIndex === selectedIndex;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => {
                          item.action();
                          onClose();
                        }}
                        onMouseEnter={() => setSelectedIndex(globalIndex)}
                        className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors duration-100 ${
                          isSelected
                            ? "bg-primary-50/80 text-ink"
                            : "text-ink-secondary hover:bg-surface-sunken hover:text-ink"
                        }`}
                      >
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface-panel text-primary-600">
                          <Icon name={item.icon} size={18} />
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="text-body font-medium truncate">{item.label}</div>
                          <div className="text-caption text-ink-muted truncate">{item.description}</div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              ))}
            </>
          )}
        </div>

        <div className="border-t border-surface-border px-4 py-2 text-caption text-ink-muted flex items-center justify-between">
          <span>{t("cmd.footer")}</span>
          <kbd className="px-1.5 py-0.5 text-[10px] font-mono bg-surface-sunken rounded">
            {typeof navigator !== "undefined" && navigator.platform.includes("Mac") ? "⌘K" : "Ctrl+K"}
          </kbd>
        </div>
      </div>
    </div>,
    document.body
  );
}