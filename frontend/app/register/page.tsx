"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { useToast } from "@/components/Toast";
import { api, apiErrorMessage, setToken } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const { showToast } = useToast();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await api.auth.register({ full_name: fullName, email, password });
      // Log the new user straight in so the first flow has no extra steps.
      const result = await api.auth.login({ email, password });
      setToken(result.access_token);
      showToast("Akaunti imetengenezwa. Karibu!", "success");
      router.push("/upload");
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
      <aside className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-primary-900 p-10 text-white lg:flex">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10">
            <Icon name="chart-line" size={20} />
          </span>
          <span className="text-h3">StatFlow</span>
        </div>

        <div className="max-w-md">
          <h2 className="text-display text-white">Anza kuchambua data sasa</h2>
          <p className="mt-3 text-body-lg text-primary-100">
            Kuhusu muhula mmoja, na una njia nzima ya uchambuzi mikononi mwako:
            pakia → safisha → chambua → chati → ripoti.
          </p>
          <ol className="mt-8 space-y-4">
            {[
              { label: "Pakia", description: "CSV, Excel, JSON, TSV, TXT au Parquet" },
              { label: "Safisha", description: "Ondoa kasoro kwenye Data Studio" },
              { label: "Chambua", description: "Uchambuzi wa takwimu wenye uthibitisho" },
              { label: "Ripoti", description: "PDF au Excel kwa kubonyeza moja" },
            ].map((step, index) => (
              <li key={step.label} className="flex items-center gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white/10 text-body font-medium">
                  {index + 1}
                </span>
                <div>
                  <p className="text-body-lg font-medium text-white">{step.label}</p>
                  <p className="text-body text-primary-100">{step.description}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>

        <p className="text-caption text-primary-100">
          Data yako imelindwa · kila mtumiaji anaona datasets zake tu
        </p>
      </aside>

      <div className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          <div className="mb-8 flex flex-col items-center text-center lg:items-start lg:text-left">
            <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary-600 text-white lg:hidden">
              <Icon name="chart-line" size={22} />
            </span>
            <h1 className="mt-4 text-h1 text-primary-900 lg:mt-0">Sajili akaunti</h1>
            <p className="mt-1 text-body text-neutral-600">
              Muhula mmoja (dakika moja) na unaanza kuchambua data
            </p>
          </div>

          <form
            onSubmit={handleSubmit}
            className="space-y-4 rounded border border-neutral-200 bg-white p-6"
          >
            <div>
              <label htmlFor="full_name" className="block text-body text-neutral-900">
                Jina kamili
              </label>
              <input
                id="full_name"
                required
                minLength={2}
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                className="mt-1 h-10 w-full rounded border border-neutral-200 px-3 text-body outline-none focus:border-primary-500"
                placeholder="Asha Mwangi"
              />
            </div>

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
                Neno la siri (angalau herufi 6)
              </label>
              <input
                id="password"
                type="password"
                required
                minLength={6}
                autoComplete="new-password"
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
              Sajili na uingie
            </Button>

            <p className="text-center text-body text-neutral-600">
              Una akaunti tayari?{" "}
              <Link href="/login" className="text-primary-600 hover:underline">
                Ingia
              </Link>
            </p>
          </form>
        </div>
      </div>
    </main>
  );
}