"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { Button } from "@/components/Button";
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
    description: "Takwimu kamili bila kuandika code — au uliza msaidizi wa AI.",
  },
  {
    icon: "file-text",
    title: "Ripoti ya kubonyeza moja",
    description: "Tengeneza PDF au Excel yenye matokeo na chati zote.",
  },
];

function BrandPanel() {
  return (
    <aside className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-primary-900 p-10 text-white lg:flex">
      <div className="flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10">
          <Icon name="chart-line" size={20} />
        </span>
        <span className="text-h3">StatFlow</span>
      </div>

      <div className="max-w-md">
        <h2 className="text-display text-white">
          Chambua data bila kuandika code
        </h2>
        <p className="mt-3 text-body-lg text-primary-100">
          Mtiririko wa hatua 6 — pakia, angalia, safisha, chambua, buni chati,
          tengeneza ripoti. Yote katika mfumo mmoja.
        </p>
        <ol className="mt-8 space-y-5">
          {VALUE_POINTS.map((point) => (
            <li key={point.title} className="flex items-start gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded bg-white/10">
                <Icon name={point.icon} size={18} />
              </span>
              <div>
                <p className="text-body-lg font-medium text-white">{point.title}</p>
                <p className="text-body text-primary-100">{point.description}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>

      <p className="text-caption text-primary-100">
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
    <main className="flex min-h-screen bg-neutral-50">
      <BrandPanel />

      <div className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          <div className="mb-8 flex flex-col items-center text-center lg:items-start lg:text-left">
            <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary-600 text-white lg:hidden">
              <Icon name="chart-line" size={22} />
            </span>
            <h1 className="mt-4 text-h1 text-primary-900 lg:mt-0">Karibu tena</h1>
            <p className="mt-1 text-body text-neutral-600">
              Ingia ili kuendelea na uchambuzi wa data yako
            </p>
          </div>

          <form
            onSubmit={handleSubmit}
            className="space-y-4 rounded border border-neutral-200 bg-white p-6"
          >
            <div>
              <label htmlFor="email" className="block text-body text-neutral-900">
                Barua pepe (email)
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="mt-1 h-10 w-full rounded border border-neutral-200 px-3 text-body outline-none focus:border-primary-500"
                placeholder="jina@example.com"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-body text-neutral-900">
                Neno la siri (password)
              </label>
              <input
                id="password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="mt-1 h-10 w-full rounded border border-neutral-200 px-3 text-body outline-none focus:border-primary-500"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <p
                role="alert"
                className="flex items-center gap-2 rounded bg-danger-bg px-3 py-2 text-body text-danger"
              >
                <Icon name="close" size={16} />
                {error}
              </p>
            )}

            <Button type="submit" size="large" loading={loading} className="w-full">
              Ingia
            </Button>

            <p className="text-center text-body text-neutral-600">
              Huna akaunti?{" "}
              <Link href="/register" className="text-primary-600 hover:underline">
                Sajili hapa
              </Link>
            </p>
          </form>
        </div>
      </div>
    </main>
  );
}