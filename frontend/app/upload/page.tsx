"use client";

import { useRouter } from "next/navigation";
import { DragEvent, useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { SelectInput } from "@/components/Field";
import { Icon } from "@/components/Icon";
import { useToast } from "@/components/Toast";
import { api, apiErrorMessage, OrgProject, Organization } from "@/lib/api";
import {
  UPLOAD_FILE_EXTENSION_LIST,
  UPLOAD_FILE_GROUPS,
  UPLOAD_FILE_INPUT_ACCEPT,
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
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [queue, setQueue] = useState<QueuedFile[]>([]);
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [selectedOrg, setSelectedOrg] = useState<number | "">("");
  const [projects, setProjects] = useState<OrgProject[]>([]);
  const [selectedProject, setSelectedProject] = useState<number | "">("");

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

  function validate(candidate: File): string | null {
    if (!isAcceptedUploadName(candidate.name)) {
      return `Aina ya faili haikusajiliwa. Pakia faili la ${UPLOAD_FILE_EXTENSION_LIST} pekee.`;
    }
    if (candidate.size > MAX_MB * 1024 * 1024) {
      return `Faili ni kubwa mno. Ukubwa wa juu ni ${MAX_MB}MB.`;
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
        setError(
          `Umechagua faili ${merged.length}. Kipakio cha moja hukubali ${MAX_FILES} faili.`
        );
        return merged.slice(0, MAX_FILES);
      }
      setError(null);
      return merged;
    });
    setProgress(0);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
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
        showToast(
          `Faili ${result.uploaded_count} zimepakiwa`,
          "success"
        );
      } else {
        // Partial success is stated plainly, with the count that actually
        // landed — a green toast over a batch where a third failed would be a
        // lie the user only discovers later.
        showToast(
          `Faili ${result.uploaded_count} zimepakiwa, ${result.failed_count} zimeshindwa`,
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
      title="Pakia data"
      description={`Aina zinazokubalika: ${UPLOAD_FILE_GROUPS}. Ukubwa wa juu ${MAX_MB}MB. Mfumo unasafisha na kuchambua moja kwa moja.`}
    >
      {orgs.length > 0 && (
        <Card
          title="Weka data kwenye mradi"
          icon="folder"
          description="Ikiwa uchague mradi, wanachama wa shirika hilo wataweza kufikia data kulingana na kiwango chao. Ikiwa hutaki, data itabaki yawewe pekee."
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <SelectInput
              label="Shirika"
              value={selectedOrg}
              options={[
                { value: "", label: "Data ya binafsi (Bila mradi)" },
                ...orgs.map((org) => ({
                  value: String(org.id),
                  label:
                    org.my_role === "viewer"
                      ? `${org.name} (mtazamaji)`
                      : org.name,
                })),
              ]}
              onChange={(event) =>
                changeOrg(event.target.value === "" ? "" : Number(event.target.value))
              }
            />
            <SelectInput
              label="Mradi"
              value={selectedProject}
              disabled={selectedOrg === ""}
              placeholder="— Bila mradi —"
              hint={
                selectedOrg === "" ? "Chagua shirika kwanza" : "Chagua mradi wa kuhifadhi data"
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

      <Card>
        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          className={`rounded-md border-2 border-dashed px-6 py-12 text-center transition-colors duration-200 ease-standard ${
            dragging
              ? "border-primary-500 bg-primary-50"
              : "border-surface-border-strong bg-surface-sunken"
          }`}
        >
          <span
            className={`mx-auto flex h-12 w-12 items-center justify-center rounded-full transition-colors duration-200 ${
              dragging ? "bg-primary-100 text-primary-700" : "bg-surface-panel text-ink-muted"
            }`}
          >
            <Icon name="upload" size={24} />
          </span>
          <p className="mt-3 text-body-lg font-medium text-ink">
            Kokota faili zako hapa (drag &amp; drop)
          </p>
          <p className="mt-1 text-body text-ink-secondary">
            au chagua faili kutoka kompyuta — unaweza chagua zaidi ya moja
          </p>
          <p className="mt-1 text-caption text-ink-muted">
            {UPLOAD_FILE_GROUPS} · hadi {MAX_MB}MB kwa faili · hadi {MAX_FILES} faili
          </p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={UPLOAD_FILE_INPUT_ACCEPT}
            className="hidden"
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
          <Button
            variant="secondary"
            className="mt-4"
            onClick={() => inputRef.current?.click()}
          >
            <Icon name="folder" size={16} />
            Chagua faili
          </Button>
        </div>

        {queue.length > 0 && (
          <div className="mt-6 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-body font-medium text-ink">
                Faili zilizochaguliwa ({ready.length})
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
                  Ondoa zote
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
                      aria-label={`Ondoa ${entry.file.name}`}
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
                  Faili {rejected.length} hazitawekwa kwa kuwa hazikubaliwa. Ondoa
                  au.badilisha ili kuendelea.
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
                  aria-label="Maendeleo ya upakiaji"
                  className="h-2 w-full overflow-hidden rounded-full bg-surface-sunken"
                >
                  <div
                    className="h-full rounded-full bg-primary-600 transition-all duration-200 ease-standard"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <p className="mt-1.5 text-caption text-ink-secondary">
                  Inapakia faili {ready.length} · {(totalBytes / 1024 / 1024).toFixed(2)} MB ·{" "}
                  {progress}%
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
                ? `Pakia faili ${ready.length}`
                : "Pakia na uchambue"}
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

      <Card title="Vidokezo vya faili lako" icon="info" description="Ili matokeo yawe bora:">
        <ul className="list-disc space-y-1.5 pl-5 text-body text-ink-secondary">
          <li>Row ya kwanza iwe majina ya columns (header).</li>
          <li>Columns za namba zisiwe na alama kama &quot;TSh&quot; au &quot;%&quot;.</li>
          <li>Tarehe ziwe katika muundo mmoja (YYYY-MM-DD inapendekezwa).</li>
          <li>
            Faili za Stata (.dta), SPSS (.sav, .zsav, .por) na R (.RData, .rda,
            .rds) zinakubalika; lebo za thamani (value labels) huhifadhiwa kama
            namba ili columns hizo zipate kubalika na kuchambuliwa.
          </li>
          <li>
            Faili kubwa (safu 100,000+) zinasindika nyuma ya pazia unaweza kuendelea
            kutumia mfumo.
          </li>
        </ul>
      </Card>
    </AppShell>
  );
}



