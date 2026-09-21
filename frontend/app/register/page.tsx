"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { Button } from "@/components/Button";
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
    <main className="flex min-h-screen items-center justify-center bg-neutral-50 px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <h1 className="text-h1 text-primary-900">Sajili akaunti</h1>
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
            <p role="alert" className="rounded bg-danger-bg px-3 py-2 text-body text-danger">
              ⚠ {error}
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
    </main>
  );
}
