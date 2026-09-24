"use client";

import { useRouter } from "next/navigation";
import { DragEvent, useRef, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { useToast } from "@/components/Toast";
import { api, apiErrorMessage } from "@/lib/api";

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
      const result = await api.datasets.upload(file, (event) => {
        if (event.total) {
          setProgress(Math.round((event.loaded / event.total) * 100));
        }
      });
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
      <Card>
        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          className={`rounded border-2 border-dashed p-8 text-center transition-colors duration-200 ${
            dragging ? "border-primary-500 bg-primary-50" : "border-neutral-200 bg-neutral-50"
          }`}
        >
          <p className="text-body-lg text-neutral-900">
            Kokota faili lako hapa (drag &amp; drop)
          </p>
          <p className="mt-1 text-body text-neutral-600">au chagua faili kutoka kompyuta</p>
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
            Chagua faili
          </Button>
        </div>

        {file && (
          <div className="mt-6 space-y-3">
            <p className="text-body text-neutral-900">
              {file.name}{" "}
              <span className="text-neutral-600">
                ({(file.size / 1024 / 1024).toFixed(2)} MB)
              </span>
            </p>

            {uploading && (
              <div>
                <div
                  role="progressbar"
                  aria-valuenow={progress}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label="Upload progress"
                  className="h-2 w-full overflow-hidden rounded bg-neutral-200"
                >
                  <div
                    className="h-full bg-primary-600 transition-all duration-200 ease-out"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <p className="mt-1 text-caption text-neutral-600">
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
          <p role="alert" className="mt-4 rounded bg-danger-bg px-3 py-2 text-body text-danger">
            ⚠ {error}
          </p>
        )}
      </Card>

      <Card title="Vidokezo vya faili lako" description="Ili matokeo yawe bora:">
        <ul className="list-disc space-y-1 pl-5 text-body text-neutral-600">
          <li>Row ya kwanza iwe majina ya columns (header).</li>
          <li>Columns za namba zisiwe na alama kama &quot;TSh&quot; au &quot;%&quot;.</li>
          <li>Tarehe ziwe katika muundo mmoja (YYYY-MM-DD inapendekezwa).</li>
          <li>
            Faili kubwa (safu 100,000+) zinasindika nyuma ya pazia — unaweza kuendelea
            kutumia mfumo.
          </li>
        </ul>
      </Card>
    </AppShell>
  );
}
