"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { Button } from "@/components/Button";
import { TextInput } from "@/components/Field";
import { Icon, IconName } from "@/components/Icon";
import { useToast } from "@/components/Toast";
import { api, apiErrorMessage, setToken } from "@/lib/api";

const VALUE_POINTS: { icon: IconName; title: string; description: string }[] = [
  {
    icon: "upload",
    title: "Pakia kwa haraka",
    description: "CSV, Excel, JSON, TSV, TXT au Parquet, hadi 50MB.",
  },
  {
    icon: "calculator",
    title: "Chambua moja kwa moja",
    description: "Takwimu kamili bila kuandika code au uliza msaidizi wa AI.",
  },
  {
    icon: "file-text",
    title: "Ripoti ya kubonyeza moja",
    description: "Tengeneza PDF au Excel yenye matokeo na chati zote.",
  },
];

function BrandPanel() {
  return (
    <aside className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-sidebar p-10 text-white lg:flex">
      <div className="flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-md bg-primary-600">
          <Icon name="chart-line" size={20} />
        </span>
        <span className="text-h3">StatFlow</span>
      </div>

      <div className="max-w-md">
        <h2 className="text-display text-white">Chambua data bila kuandika code</h2>
        <p className="mt-3 text-body-lg text-neutral-300">
          Mtiririko wa hatua 6: pakia, angalia, safisha, chambua, buni chati, tengeneza
          ripoti. Yote katika mfumo mmoja.
        </p>
        <ol className="mt-8 space-y-5">
          {VALUE_POINTS.map((point) => (
            <li key={point.title} className="flex items-start gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-white/10 text-primary-300">
                <Icon name={point.icon} size={18} />
              </span>
              <div>
                <p className="text-body-lg font-medium text-white">{point.title}</p>
                <p className="text-body text-neutral-400">{point.description}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>

      <p className="text-caption text-neutral-500">
        Mfumo wenye usalama · data yako imelindwa kwa kila mtumiaji
      </p>
    </aside>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const { showToast } = useToast();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = await api.auth.login({ email, password });
      setToken(result.access_token);
      showToast("Umeingia kikamilifu. Karibu!", "success");
      router.push("/dashboard");
    } catch (caught) {
      const message = apiErrorMessage(caught);
      setError(message);
      showToast(message, "danger");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen bg-surface-canvas">
      <BrandPanel />

      <div className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          <div className="mb-8 flex flex-col items-center text-center lg:items-start lg:text-left">
            <span className="flex h-11 w-11 items-center justify-center rounded-md bg-primary-600 text-white lg:hidden">
              <Icon name="chart-line" size={22} />
            </span>
            <h1 className="mt-4 text-h1 text-ink lg:mt-0">Karibu tena</h1>
            <p className="mt-1 text-body text-ink-secondary">
              Ingia ili kuendelea na uchambuzi wa data yako
            </p>
          </div>

          <form
            onSubmit={handleSubmit}
            className="space-y-4 rounded-md border border-surface-border bg-surface-panel p-6 shadow-card"
          >
            <TextInput
              label="Barua pepe (email)"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="jina@example.com"
            />

            <TextInput
              label="Neno la siri (password)"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••"
            />

            {error && (
              <p
                role="alert"
                className="flex items-start gap-2 rounded-md border border-danger/30 bg-danger-bg px-3 py-2.5 text-body text-danger-700"
              >
                <Icon name="alert-circle" size={16} className="mt-0.5 shrink-0" />
                {error}
              </p>
            )}

            <Button type="submit" size="large" loading={loading} className="w-full">
              Ingia
            </Button>

            <p className="text-center text-body text-ink-secondary">
              Huna akaunti?{" "}
              <Link
                href="/register"
                className="font-medium text-primary-600 hover:text-primary-700 hover:underline"
              >
                Sajili hapa
              </Link>
            </p>
          </form>
        </div>
      </div>
    </main>
  );
}