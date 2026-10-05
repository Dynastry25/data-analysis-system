"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { Button } from "@/components/Button";
import { TextInput } from "@/components/Field";
import { Icon, IconName } from "@/components/Icon";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { Logo, LogoMark } from "@/components/Logo";
import { useToast } from "@/components/Toast";
import { api, apiErrorMessage, setToken } from "@/lib/api";
import { useLanguage, type TranslationKey } from "@/lib/i18n";

/**
 * The three selling points. They are keys rather than strings so the panel
 * follows the language switcher -- a Swahili user reading an English pitch on
 * the sign-in screen, which is the one screen they cannot navigate away from.
 */
const VALUE_POINTS: {
  icon: IconName;
  title: TranslationKey;
  description: TranslationKey;
}[] = [
  {
    icon: "upload",
    title: "auth.pointUploadTitle",
    description: "auth.pointUploadBody",
  },
  {
    icon: "calculator",
    title: "auth.pointAnalyseTitle",
    description: "auth.pointAnalyseBody",
  },
  {
    icon: "file-text",
    title: "auth.pointReportTitle",
    description: "auth.pointReportBody",
  },
];

function BrandPanel() {
  const { t } = useLanguage();
  return (
    <aside className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-sidebar p-10 text-white lg:flex">
      <Logo />

      <div className="max-w-md">
        <h2 className="text-display text-white">{t("auth.headline")}</h2>
        <p className="mt-3 text-body-lg text-neutral-300">
          {t("auth.subheadline")}
        </p>
        <ol className="mt-8 space-y-5">
          {VALUE_POINTS.map((point) => (
            <li key={point.title} className="flex items-start gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-white/10 text-primary-300">
                <Icon name={point.icon} size={18} />
              </span>
              <div>
                <p className="text-body-lg font-medium text-white">
                  {t(point.title)}
                </p>
                <p className="text-body text-neutral-400">
                  {t(point.description)}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </div>

      <p className="text-caption text-neutral-500">{t("auth.footer")}</p>
    </aside>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const { showToast } = useToast();
  const { t } = useLanguage();
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
      showToast(t("auth.signedIn"), "success");
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

      <div className="relative flex flex-1 items-center justify-center px-4 py-12">
        {/*
          The switch lives on the auth screens too. The sidebar one is out of
          reach until you are already signed in, so a Swahili speaker otherwise
          had no way to reach their language before logging in.
        */}
        <div className="absolute right-5 top-5">
          <LanguageSwitcher />
        </div>

        <div className="w-full max-w-md">
          <div className="mb-8 flex flex-col items-center text-center lg:items-start lg:text-left">
            <LogoMark size={44} className="lg:hidden" />
            <h1 className="mt-4 text-h1 text-ink lg:mt-0">
              {t("auth.welcomeBack")}
            </h1>
            <p className="mt-1 text-body text-ink-secondary">
              {t("auth.loginIntro")}
            </p>
          </div>

          <form
            onSubmit={handleSubmit}
            className="space-y-4 rounded-md border border-surface-border bg-surface-panel p-6 shadow-card"
          >
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
              {t("auth.signIn")}
            </Button>

            <p className="text-center text-body text-ink-secondary">
              {t("auth.noAccount")}{" "}
              <Link
                href="/register"
                className="font-medium text-primary-600 hover:text-primary-700 hover:underline"
              >
                {t("auth.createOne")}
              </Link>
            </p>
          </form>
        </div>
      </div>
    </main>
  );
}