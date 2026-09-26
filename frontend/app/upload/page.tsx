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

const ALLOWED = [".csv", ".xlsx", ".json", ".tsv", ".txt", ".parquet"];
const MAX_MB = 50;

export default function UploadPage() {
  const router = useRouter();
  const { showToast } = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
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
    const lower = candidate.name.toLowerCase();
    if (!ALLOWED.some((extension) => lower.endsWith(extension))) {
      return "File type not supported. Pakia faili la .csv, .xlsx, .json, .tsv, .txt au .parquet pekee.";
    }
    if (candidate.size > MAX_MB * 1024 * 1024) {
      return `File too large. Maximum allowed size is ${MAX_MB}MB.`;
    }
    return null;
  }

  function pick(candidate: File | undefined) {
    if (!candidate) return;
    const problem = validate(candidate);
    setError(problem);
    setFile(problem ? null : candidate);
    setProgress(0);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    pick(event.dataTransfer.files?.[0]);
  }

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setError(null);
    setProgress(0);
    try {
      const result = await api.datasets.upload(
        file,
        (event) => {
          if (event.total) {
            setProgress(Math.round((event.loaded / event.total) * 100));
          }
        },
        selectedProject === "" ? null : selectedProject
      );
      showToast(
        `Data imepakiwa: safu ${result.row_count}, columns ${result.column_count}`,
        "success"
      );
      router.push(`/datasets/${result.dataset_id}`);
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
      description="CSV, Excel (.xlsx), JSON, TSV, TXT au Parquet, hadi 50MB. Mfumo unasafisha na kuchambua moja kwa moja."
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
          className={`rounded-lg border-2 border-dashed px-6 py-12 text-center transition-colors duration-200 ease-standard ${
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
            Kokota faili lako hapa (drag &amp; drop)
          </p>
          <p className="mt-1 text-body text-ink-secondary">
            au chagua faili kutoka kompyuta
          </p>
          <p className="mt-1 text-caption text-ink-muted">
            CSV, Excel (.xlsx), JSON, TSV, TXT au Parquet · hadi {MAX_MB}MB
          </p>
          <input
            ref={inputRef}
            type="file"
            accept=".csv,.xlsx,.json,.tsv,.txt,.parquet"
            className="hidden"
            onChange={(event) => pick(event.target.files?.[0])}
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

        {file && (
          <div className="mt-6 space-y-3">
            <div className="flex items-center gap-3 rounded-md border border-surface-border bg-surface-sunken px-3.5 py-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-surface-panel text-primary-600 shadow-card">
                <Icon name="file-text" size={18} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-body font-medium text-ink">{file.name}</p>
                <p className="text-caption text-ink-muted">
                  {(file.size / 1024 / 1024).toFixed(2)} MB
                </p>
              </div>
              {!uploading && (
                <Button
                  variant="ghost"
                  size="small"
                  onClick={() => {
                    setFile(null);
                    setProgress(0);
                    setError(null);
                  }}
                >
                  Badilisha
                </Button>
              )}
            </div>

            {uploading && (
              <div>
                <div
                  role="progressbar"
                  aria-valuenow={progress}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label="Maendeleo ya upakiaji"
                  className="h-2 w-full overflow-hidden rounded-pill bg-surface-sunken"
                >
                  <div
                    className="h-full rounded-pill bg-primary-600 transition-all duration-200 ease-standard"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <p className="mt-1.5 text-caption text-ink-secondary">
                  Inapakia… {progress}%
                </p>
              </div>
            )}

            <Button size="large" loading={uploading} onClick={handleUpload}>
              Pakia na uchambue
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
            Faili kubwa (safu 100,000+) zinasindika nyuma ya pazia unaweza kuendelea
            kutumia mfumo.
          </li>
        </ul>
      </Card>
    </AppShell>
  );
}



