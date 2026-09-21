"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { Button } from "@/components/Button";
import { useToast } from "@/components/Toast";
import { api, apiErrorMessage, setToken } from "@/lib/api";

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
      router.push("/datasets");
    } catch (caught) {
      const message = apiErrorMessage(caught);
      setError(message);
      showToast(message, "danger");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-neutral-50 px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <h1 className="text-h1 text-primary-900">Data Analysis Platform</h1>
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
            <p role="alert" className="rounded bg-danger-bg px-3 py-2 text-body text-danger">
              ⚠ {error}
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
    </main>
  );
}
