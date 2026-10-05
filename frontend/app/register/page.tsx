"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { Button } from "@/components/Button";
import { TextInput } from "@/components/Field";
import { Icon } from "@/components/Icon";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { LogoMark } from "@/components/Logo";
import { useToast } from "@/components/Toast";
import { api, apiErrorMessage, setToken } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";

export default function RegisterPage() {
  const router = useRouter();
  const { showToast } = useToast();
  const { t } = useLanguage();
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
      showToast(t("auth.accountCreated"), "success");
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
    <main className="flex min-h-screen bg-surface-canvas">
      <aside className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-sidebar p-10 text-white lg:flex">
        <div>
          <h2 className="text-display text-white">{t("auth.registerHeadline")}</h2>
          <p className="mt-3 text-body-lg text-neutral-300">
            {t("auth.registerSubheadline")}
          </p>
          <ol className="mt-8 space-y-4">
            {[
              { label: t("auth.stepUpload"), description: t("upload.formats") },
              { label: t("auth.stepClean"), description: t("auth.stepCleanBody") },
              { label: t("auth.stepAnalyse"), description: t("auth.stepAnalyseBody") },
              { label: t("auth.stepReport"), description: t("auth.stepReportBody") },
            ].map((step, index) => (
              <li key={step.label} className="flex items-center gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white/10 text-body font-medium text-primary-300">
                  {index + 1}
                </span>
                <div>
                  <p className="text-body-lg font-medium text-white">{step.label}</p>
                  <p className="text-body text-neutral-400">{step.description}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>

        <p className="text-caption text-neutral-500">{t("auth.registerFooter")}</p>
      </aside>

      <div className="relative flex flex-1 items-center justify-center px-4 py-12">
        <div className="absolute right-5 top-5">
          <LanguageSwitcher />
        </div>

        <div className="w-full max-w-md">
          <div className="mb-8 flex flex-col items-center text-center lg:items-start lg:text-left">
            <LogoMark size={44} className="lg:hidden" />
            <h1 className="mt-4 text-h1 text-ink lg:mt-0">
              {t("auth.registerTitle")}
            </h1>
            <p className="mt-1 text-body text-ink-secondary">
              {t("auth.registerIntro")}
            </p>
          </div>

          <form
            onSubmit={handleSubmit}
            className="space-y-4 rounded-md border border-surface-border bg-surface-panel p-6 shadow-card"
          >
            <TextInput
              label={t("auth.fullName")}
              required
              minLength={2}
              autoComplete="name"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              placeholder={t("auth.namePlaceholder")}
            />

            <TextInput
              label={t("auth.email")}
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="name@example.com"
            />

            <TextInput
              label={t("auth.password")}
              hint={t("auth.passwordHint")}
              type="password"
              required
              minLength={6}
              autoComplete="new-password"
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
              {t("auth.registerSubmit")}
            </Button>

            <p className="text-center text-body text-ink-secondary">
              {t("auth.haveAccount")}{" "}
              <Link
                href="/login"
                className="font-medium text-primary-600 hover:text-primary-700 hover:underline"
              >
                {t("auth.signInInstead")}
              </Link>
            </p>
          </form>
        </div>
      </div>
    </main>
  );
}