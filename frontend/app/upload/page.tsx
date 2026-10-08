"use client";

import { useRouter } from "next/navigation";
import { DragEvent, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { SelectInput, TextInput } from "@/components/Field";
import { Icon } from "@/components/Icon";
import { useToast } from "@/components/Toast";
import {
  api,
  apiErrorMessage,
  OrgProject,
  Organization,
  ScrapePreviewResponse,
} from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import {
  UPLOAD_FILE_EXTENSION_LIST,
  UPLOAD_FILE_GROUPS,
  UPLOAD_FILE_INPUT_ACCEPT,
  UPLOAD_FORMATS,
  isAcceptedUploadName,
} from "@/lib/upload-formats";

const MAX_MB = 50;
/** How many files one batch may carry; mirrors MAX_BATCH_FILES on the backend. */
const MAX_FILES = 20;

interface QueuedFile {
  file: File;
  /** Set when this file cannot be sent, with the reason. */
  problem: string | null;
}

export default function UploadPage() {
  const router = useRouter();
  const { showToast } = useToast();
  const { t } = useLanguage();
  const [dragging, setDragging] = useState(false);
  const [queue, setQueue] = useState<QueuedFile[]>([]);
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [selectedOrg, setSelectedOrg] = useState<number | "">("");
  const [projects, setProjects] = useState<OrgProject[]>([]);
  const [selectedProject, setSelectedProject] = useState<number | "">("");
  // Web-scrape source: the preview is bound to the URL it came from, so the
  // import always resubmits that exact URL with the chosen table index.
  const [scrapeUrl, setScrapeUrl] = useState("");
  const [scraping, setScraping] = useState(false);
  const [scrapeResult, setScrapeResult] = useState<ScrapePreviewResponse | null>(
    null
  );
  const [scrapeSelection, setScrapeSelection] = useState<number | null>(null);
  const [importing, setImporting] = useState(false);
  const [scrapeError, setScrapeError] = useState<string | null>(null);

  useEffect(() => {
    api.organizations
      .list()
      .then((list) => setOrgs(list))
      .catch(() => setOrgs([]));
  }, []);

  useEffect(() => {
    if (selectedOrg === "") {
      setProjects([]);
      return;
    }
    let active = true;
    api.organizations
      .projects(selectedOrg as number)
      .then((list) => {
        if (active) setProjects(list);
      })
      .catch(() => {
        if (active) setProjects([]);
      });
    return () => {
      active = false;
    };
  }, [selectedOrg]);

  function changeOrg(value: number | "") {
    setSelectedOrg(value);
    setSelectedProject("");
  }

  function changeScrapeUrl(value: string) {
    setScrapeUrl(value);
    // The preview belongs to the URL it was fetched from; editing the URL must
    // not leave a stale table list whose import would target something else.
    setScrapeResult(null);
    setScrapeSelection(null);
    setScrapeError(null);
  }

  async function handleFindTables() {
    const url = scrapeUrl.trim();
    if (!url) return;
    setScraping(true);
    setScrapeError(null);
    setScrapeResult(null);
    setScrapeSelection(null);
    try {
      setScrapeResult(await api.scrape.preview(url));
    } catch (caught) {
      setScrapeError(apiErrorMessage(caught));
    } finally {
      setScraping(false);
    }
  }

  async function handleImportTable() {
    if (!scrapeResult || scrapeSelection === null) return;
    setImporting(true);
    setScrapeError(null);
    try {
      const created = await api.scrape.importTable({
        url: scrapeResult.url,
        table_index: scrapeSelection,
        project_id: selectedProject === "" ? null : selectedProject,
      });
      showToast(
        t("scrape.imported", { name: created.original_filename }),
        "success"
      );
      router.push(`/datasets/${created.dataset_id}`);
    } catch (caught) {
      const message = apiErrorMessage(caught);
      setScrapeError(message);
      showToast(message, "danger");
    } finally {
      setImporting(false);
    }
  }

  function validate(candidate: File): string | null {
    if (!isAcceptedUploadName(candidate.name)) {
      return t("upload.errType", { list: UPLOAD_FILE_EXTENSION_LIST });
    }
    if (candidate.size > MAX_MB * 1024 * 1024) {
      return t("upload.errSize", { max: MAX_MB });
    }
    return null;
  }

  /*
   * Files are added to the queue rather than replacing it, so choosing twice
   * in a row adds to the selection instead of silently discarding the first
   * pick — the thing people hit when they pick a folder in two goes.
   *
   * A file that fails validation stays in the list, marked, rather than being
   * dropped on the floor: "why is my file not uploading" is a much worse
   * experience than seeing the reason next to the name. Only the valid ones
   * are sent.
   */
  function addFiles(incoming: FileList | File[] | null | undefined) {
    if (!incoming) return;
    const added = Array.from(incoming).map((file) => ({
      file,
      problem: validate(file),
    }));
    setQueue((current) => {
      const merged = [...current];
      for (const item of added) {
        // The same file twice in one batch is a mistake, and the backend would
        // store it twice; replacing the older entry is the least surprising fix.
        const sameName = merged.findIndex(
          (entry) =>
            entry.file.name === item.file.name &&
            entry.file.size === item.file.size &&
            entry.file.lastModified === item.file.lastModified
        );
        if (sameName >= 0) merged[sameName] = item;
        else merged.push(item);
      }
      if (merged.length > MAX_FILES) {
        setError(t("upload.errTooMany", { count: merged.length, max: MAX_FILES }));
        return merged.slice(0, MAX_FILES);
      }
      setError(null);
      return merged;
    });
    setProgress(0);
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    addFiles(event.dataTransfer.files);
  }

  const ready = queue.filter((entry) => !entry.problem);
  const rejected = queue.filter((entry) => entry.problem);
  const totalBytes = ready.reduce((sum, entry) => sum + entry.file.size, 0);

  async function handleUpload() {
    if (ready.length === 0) return;
    setUploading(true);
    setError(null);
    setProgress(0);
    try {
      // One file still goes through the batch endpoint: two code paths here
      // would mean two places for the upload to go wrong.
      const result = await api.datasets.uploadBatch(
        ready.map((entry) => entry.file),
        (event) => {
          if (event.total) {
            setProgress(Math.round((event.loaded / event.total) * 100));
          }
        },
        selectedProject === "" ? null : selectedProject
      );

      const failed = result.results.filter((entry) => entry.status === "failed");
      const first = result.results.find((entry) => entry.dataset_id);

      if (failed.length === 0) {
        showToast(t("upload.toastOk", { count: result.uploaded_count }), "success");
      } else {
        // Partial success is stated plainly, with the count that actually
        // landed — a green toast over a batch where a third failed would be a
        // lie the user only discovers later.
        showToast(
          t("upload.toastPartial", {
            ok: result.uploaded_count,
            failed: result.failed_count,
          }),
          "warning"
        );
      }

      if (ready.length === 1 && first?.dataset_id) {
        router.push(`/datasets/${first.dataset_id}`);
        return;
      }
      // Several datasets now exist, so there is no single page to open: send
      // the user to the list where all of them are.
      router.push("/datasets");
    } catch (caught) {
      const message = apiErrorMessage(caught);
      setError(message);
      showToast(message, "danger");
    } finally {
      setUploading(false);
    }
  }

  return (
    <AppShell
      eyebrow={t("upload.eyebrow")}
      title={t("upload.title")}
      description={t("upload.description", {
        formats: UPLOAD_FILE_GROUPS,
        max: MAX_MB,
      })}
    >
      {orgs.length > 0 && (
        <Card
          title={t("upload.project.title")}
          icon="folder"
          description={t("upload.project.body")}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <SelectInput
              label={t("upload.project.org")}
              value={selectedOrg}
              options={[
                { value: "", label: t("upload.project.personal") },
                ...orgs.map((org) => ({
                  value: String(org.id),
                  label:
                    org.my_role === "viewer"
                      ? `${org.name} (${t("upload.project.viewer")})`
                      : org.name,
                })),
              ]}
              onChange={(event) =>
                changeOrg(event.target.value === "" ? "" : Number(event.target.value))
              }
            />
            <SelectInput
              label={t("upload.project.project")}
              value={selectedProject}
              disabled={selectedOrg === ""}
              placeholder={t("upload.project.noProject")}
              hint={
                selectedOrg === ""
                  ? t("upload.project.pickOrg")
                  : t("upload.project.pickProject")
              }
              options={projects.map((project) => ({
                value: String(project.id),
                label: project.name,
              }))}
              onChange={(event) =>
                setSelectedProject(
                  event.target.value === "" ? "" : Number(event.target.value)
                )
              }
            />
          </div>
        </Card>
      )}

      <Card
        title={t("upload.file.title")}
        icon="upload"
        description={t("upload.file.body")}
      >
        {/* The zone is a <label>, so the whole surface is clickable and the native
          file input supplies keyboard and screen-reader behaviour for free.
          A div with an onClick would need role, tabIndex and key handlers to
          match that, and would still not announce the file dialog correctly. */}
        <label
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-[11px] border-[1.5px] border-dashed px-6 py-11 text-center transition-colors duration-200 ease-standard focus-within:border-primary-500 focus-within:bg-primary-50 ${
            dragging
              ? "border-primary-500 bg-primary-50"
              : "border-[#CCC4DB] bg-[#FAF9FC] hover:border-primary-500 hover:bg-primary-50"
          }`}
        >
          <Icon
            name="database"
            size={26}
            className={dragging ? "text-primary-600" : "text-primary-500"}
          />
          <span className="block text-body-lg font-medium text-ink">
            {queue.length > 0 ? t("upload.dropMore") : t("upload.dropHint")}
          </span>
          <span className="block text-body text-ink-muted">
            {t("upload.dropClick")}
          </span>
          <span className="mt-1 flex flex-wrap items-center justify-center gap-1.5">
            {UPLOAD_FORMATS.map((format) => (
              <span
                key={format.label}
                className="rounded bg-surface-panel px-1.5 py-0.5 text-caption font-semibold uppercase text-ink-secondary"
              >
                {format.label}
              </span>
            ))}
          </span>
          <span className="mt-1 text-caption text-ink-muted">
            {t("upload.dropLimits", { max: MAX_MB, files: MAX_FILES })}
          </span>
          <input
            type="file"
            multiple
            accept={UPLOAD_FILE_INPUT_ACCEPT}
            className="sr-only"
            onChange={(event) => {
              addFiles(event.target.files);
              /*
               * Reset the input so choosing the same file twice in a row still
               * fires onChange. Without this the picker looks broken the second
               * time someone picks the very same file.
               */
              event.target.value = "";
            }}
          />
        </label>

        {queue.length > 0 && (
          <div className="mt-6 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-body font-medium text-ink">
                {t("upload.selected", { count: ready.length })}
              </p>
              {!uploading && (
                <Button
                  variant="ghost"
                  size="small"
                  onClick={() => {
                    setQueue([]);
                    setProgress(0);
                    setError(null);
                  }}
                >
                  {t("upload.clearAll")}
                </Button>
              )}
            </div>

            {/*
             * A list rather than one card per file: at twenty files a stack of
             * cards is a wall, and the only thing anyone needs to check is the
             * name, the size and whether anything is wrong with it.
             */}
            <ul className="divide-y divide-surface-border overflow-hidden rounded-md border border-surface-border bg-surface-panel">
              {queue.map((entry, index) => (
                <li
                  key={`${entry.file.name}-${entry.file.size}-${entry.file.lastModified}`}
                  className={`flex items-center gap-3 px-3.5 py-2.5 ${
                    entry.problem ? "bg-danger-bg/40" : ""
                  }`}
                >
                  <span
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md ${
                      entry.problem
                        ? "bg-danger-bg text-danger-700"
                        : "bg-surface-sunken text-primary-600"
                    }`}
                  >
                    <Icon
                      name={entry.problem ? "alert-circle" : "file-text"}
                      size={16}
                    />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p
                      className={`truncate text-body font-medium ${
                        entry.problem ? "text-danger-700" : "text-ink"
                      }`}
                    >
                      {entry.file.name}
                    </p>
                    <p className="text-caption text-ink-muted">
                      {entry.problem ?? `${(entry.file.size / 1024 / 1024).toFixed(2)} MB`}
                    </p>
                  </div>
                  {!uploading && (
                    <button
                      type="button"
                      onClick={() =>
                        setQueue((current) =>
                          current.filter((_, position) => position !== index)
                        )
                      }
                      aria-label={t("upload.remove", { name: entry.file.name })}
                      className="shrink-0 rounded-full p-1 text-ink-muted transition-colors duration-150 ease-standard hover:bg-surface-sunken hover:text-danger-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
                    >
                      <Icon name="close" size={16} />
                    </button>
                  )}
                </li>
              ))}
            </ul>

            {rejected.length > 0 && (
              <p className="flex items-start gap-2 text-caption text-danger-700">
                <Icon name="alert-circle" size={14} className="mt-0.5 shrink-0" />
                <span>
                  {t("upload.rejectedNotice", { count: rejected.length })}
                </span>
              </p>
            )}

            {uploading && (
              <div>
                <div
                  role="progressbar"
                  aria-valuenow={progress}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={t("upload.progressAria")}
                  className="h-2 w-full overflow-hidden rounded-full bg-surface-sunken"
                >
                  <div
                    className="h-full rounded-full bg-primary-600 transition-all duration-200 ease-standard"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <p className="mt-1.5 text-caption text-ink-secondary">
                  {t("upload.progressBody", {
                    count: ready.length,
                    mb: (totalBytes / 1024 / 1024).toFixed(2),
                    pct: progress,
                  })}
                </p>
              </div>
            )}

            <Button
              size="large"
              loading={uploading}
              disabled={ready.length === 0}
              onClick={handleUpload}
            >
              {ready.length > 1
                ? t("upload.submitMany", { count: ready.length })
                : t("upload.submitOne")}
            </Button>
          </div>
        )}

        {error && (
          <p
            role="alert"
            className="mt-4 flex items-start gap-2 rounded-md border border-danger/30 bg-danger-bg px-3 py-2.5 text-body text-danger-700"
          >
            <Icon name="alert-circle" size={16} className="mt-0.5 shrink-0" />
            {error}
          </p>
        )}
      </Card>

      <Card
        title={t("scrape.cardTitle")}
        icon="globe"
        description={t("scrape.cardBody")}
      >
        <div className="space-y-4">
          <TextInput
            label={t("scrape.urlLabel")}
            hint={t("scrape.urlHint")}
            placeholder="https://…"
            type="url"
            value={scrapeUrl}
            onChange={(event) => changeScrapeUrl(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void handleFindTables();
              }
            }}
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              loading={scraping}
              disabled={!scrapeUrl.trim() || importing}
              onClick={() => void handleFindTables()}
            >
              {scraping ? t("scrape.fetching") : t("scrape.find")}
            </Button>
            {scrapeResult && (
              <Button
                variant="ghost"
                disabled={importing}
                onClick={() => changeScrapeUrl(scrapeUrl)}
              >
                {t("scrape.clear")}
              </Button>
            )}
          </div>

          {scrapeError && (
            <p
              role="alert"
              className="flex items-start gap-2 rounded-md border border-danger/30 bg-danger-bg px-3 py-2.5 text-body text-danger-700"
            >
              <Icon name="alert-circle" size={16} className="mt-0.5 shrink-0" />
              {scrapeError}
            </p>
          )}

          {scrapeResult && (
            <div className="space-y-3">
              <p className="text-caption text-ink-secondary">
                {t("scrape.found", { count: scrapeResult.table_count })}
                {scrapeResult.title
                  ? ` · ${t("scrape.pageTitle", { title: scrapeResult.title })}`
                  : ""}
              </p>
              {/*
                A radio group, not a list of links: exactly one table can be
                imported, and aria-checked carries which. The first rows are
                shown so the choice is made by content, not by index number.
              */}
              <ul
                role="radiogroup"
                aria-label={t("scrape.cardTitle")}
                className="space-y-2"
              >
                {scrapeResult.tables.map((table) => {
                  const active = scrapeSelection === table.index;
                  const previewColumns = table.columns.slice(0, 4);
                  return (
                    <li key={table.index}>
                      <button
                        type="button"
                        role="radio"
                        aria-checked={active}
                        disabled={importing}
                        onClick={() => setScrapeSelection(table.index)}
                        className={`w-full rounded-md border px-3 py-2.5 text-left transition-colors duration-150 ease-standard ${
                          active
                            ? "border-primary-500 bg-primary-50"
                            : "border-surface-border bg-surface-panel hover:border-surface-border-strong hover:bg-surface-sunken"
                        }`}
                      >
                        <span className="flex flex-wrap items-center justify-between gap-2">
                          <span className="text-body font-medium text-ink">
                            {t("scrape.tableN", { n: table.index + 1 })}
                          </span>
                          <span className="text-caption text-ink-muted">
                            {table.row_count.toLocaleString()} {t("common.rows")} ·{" "}
                            {table.column_count} {t("common.columns")}
                          </span>
                        </span>
                        {table.row_count === 0 ? (
                          <span className="mt-1 block text-caption text-danger-700">
                            {t("scrape.emptyTable")}
                          </span>
                        ) : (
                          <span className="mt-2 block overflow-x-auto">
                            <table className="w-full table-fixed border-collapse text-caption">
                              <thead>
                                <tr className="text-left text-ink-muted">
                                  {previewColumns.map((column) => (
                                    <th
                                      key={column}
                                      className="max-w-[9rem] truncate border-b border-surface-border pb-1 pr-2 font-medium"
                                    >
                                      {column}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody className="font-mono">
                                {table.preview_rows
                                  .slice(0, 3)
                                  .map((row, rowIndex) => (
                                    <tr key={rowIndex}>
                                      {previewColumns.map((column) => (
                                        <td
                                          key={column}
                                          className="max-w-[9rem] truncate py-0.5 pr-2 text-ink-secondary"
                                        >
                                          {row[column] === null ||
                                          row[column] === undefined
                                            ? "—"
                                            : String(row[column])}
                                        </td>
                                      ))}
                                    </tr>
                                  ))}
                              </tbody>
                            </table>
                          </span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
              <div className="flex flex-wrap items-center gap-3">
                <Button
                  loading={importing}
                  disabled={scrapeSelection === null}
                  onClick={() => void handleImportTable()}
                >
                  {importing ? t("scrape.importing") : t("scrape.import")}
                </Button>
                <span className="text-caption text-ink-muted">
                  {scrapeSelection === null
                    ? t("scrape.selectHint")
                    : t("scrape.tableN", { n: scrapeSelection + 1 })}
                </span>
              </div>
            </div>
          )}
        </div>
      </Card>

      <Card
        title={t("upload.tips.title")}
        icon="info"
        description={t("upload.tips.body")}
      >
        <ul className="list-disc space-y-1.5 pl-5 text-body text-ink-secondary">
          <li>{t("upload.tips.header")}</li>
          <li>{t("upload.tips.noMarks")}</li>
          <li>{t("upload.tips.dates")}</li>
          <li>{t("upload.tips.statFiles")}</li>
          <li>{t("upload.tips.large")}</li>
        </ul>
      </Card>
    </AppShell>
  );
}



