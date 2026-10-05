"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { TextArea, TextInput } from "@/components/Field";
import { Icon } from "@/components/Icon";
import { InlineSearch } from "@/components/InlineSearch";
import { TableSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import { api, apiErrorMessage, Organization, OrgRole } from "@/lib/api";

const ROLE_TONE: Record<OrgRole, "primary" | "success" | "info" | "neutral"> = {
  owner: "primary",
  admin: "success",
  analyst: "info",
  viewer: "neutral",
};

function RoleBadge({ role }: { role: OrgRole }) {
  return <Badge tone={ROLE_TONE[role]}>{role}</Badge>;
}

export default function OrganizationsPage() {
  const { showToast } = useToast();
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState<number | null>(null);
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return organizations;
    return organizations.filter(
      (org) =>
        org.name.toLowerCase().includes(needle) ||
        org.slug.toLowerCase().includes(needle) ||
        (org.description?.toLowerCase().includes(needle) ?? false)
    );
  }, [organizations, query]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setOrganizations(await api.organizations.list());
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (name.trim().length < 2) {
      setError("Jina la shirika linapaswa kuwa angalau herufi 2.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const org = await api.organizations.create({ name: name.trim(), description });
      showToast("Shirika limetengenezwa", "success");
      setName("");
      setDescription("");
      setShowForm(false);
      if (typeof window !== "undefined") {
        window.location.href = `/organizations/${org.id}`;
      }
    } catch (caught) {
      const message = apiErrorMessage(caught);
      setError(message);
      showToast(message, "danger");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(org: Organization) {
    if (confirmingDelete !== org.id) {
      setConfirmingDelete(org.id);
      return;
    }
    try {
      await api.organizations.remove(org.id);
      showToast("Shirika limefutwa", "success");
      setConfirmingDelete(null);
      load();
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }

  return (
    <AppShell
      eyebrow="Mashirika"
      title="Mashirika"
      description="Panga watu na data kwenye mashirika, na kila mwanachama apate kiwango chake cha ruhusa."
      actions={
        <Button
          onClick={() => {
            setShowForm((value) => !value);
            setError(null);
          }}
          icon="plus"
        >
          Shirika jipya
        </Button>
      }
    >
      {showForm && (
        <Card
          title="Tengeneza shirika"
          description="Wewe utakuwa mwenyekiti (owner) wa shirika hili."
          icon="building"
        >
          <form onSubmit={handleCreate} className="space-y-4">
            <TextInput
              id="org_name"
              label="Jina la shirika"
              required
              minLength={2}
              value={name}
              error={error ?? undefined}
              onChange={(event) => {
                setName(event.target.value);
                if (error) setError(null);
              }}
              placeholder="Mfano: Shule ya Taifa"
            />
            <TextArea
              id="org_desc"
              label="Maelezo"
              optionalLabel="hiari"
              rows={2}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Shirika hili litachambua data gani?"
            />
            <div className="flex items-center gap-2">
              <Button type="submit" loading={busy} icon="check">
                Tengeneza
              </Button>
              <Button variant="ghost" onClick={() => setShowForm(false)}>
                Ghairi
              </Button>
            </div>
          </form>
        </Card>
      )}

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <InlineSearch
          value={query}
          onChange={setQuery}
          placeholder="Tafuta mashirika..."
          label="Tafuta mashirika"
        />
        <p className="text-caption text-ink-muted" aria-live="polite">
          {loading
            ? "Inapakia..."
            : `Inaonyesha ${visible.length} kati ya ${organizations.length}`}
        </p>
      </div>

      {loading ? (
        <TableSkeleton rows={3} />
      ) : organizations.length === 0 ? (
        <EmptyState
          title="Huna mashirika bado"
          description="Shirika hukusanya wanachama, miradi na data pamoja chini ya sheria zile zile."
          icon="building"
          action={
            <Button onClick={() => setShowForm(true)} icon="plus">
              Tengeneza la kwanza
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {visible.map((org) => (
            <Card key={org.id} className="flex flex-col">
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary-100 text-primary-700">
                    <Icon name="building" size={20} />
                  </span>
                  <div className="min-w-0">
                    <Link
                      href={`/organizations/${org.id}`}
                      className="block truncate text-h3 text-ink transition-colors duration-150 hover:text-primary-700"
                    >
                      {org.name}
                    </Link>
                    <p className="truncate text-caption text-ink-muted">@{org.slug}</p>
                  </div>
                </div>
                {org.my_role && <RoleBadge role={org.my_role} />}
              </div>

              {org.description && (
                <p className="mt-3 line-clamp-3 text-body text-ink-secondary">
                  {org.description}
                </p>
              )}

              <div className="mt-4 flex flex-wrap items-center gap-4 text-caption text-ink-secondary">
                <span className="inline-flex items-center gap-1.5">
                  <Icon name="users" size={16} className="text-ink-muted" />
                  {org.member_count} wanachama
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Icon name="folder" size={16} className="text-ink-muted" />
                  {org.project_count} miradi
                </span>
              </div>

              {org.my_role === "owner" && confirmingDelete === org.id ? (
                <div className="mt-4 rounded-md border border-danger/30 bg-danger-bg p-2.5">
                  <p className="text-caption text-danger-700">
                    Futa &ldquo;{org.name}&rdquo; na data yake yote? Kitendo hiki hakiwezi
                    kubatilishwa.
                  </p>
                  <div className="mt-2 flex items-center gap-2">
                    <Button
                      variant="danger"
                      size="small"
                      icon="trash"
                      onClick={() => handleDelete(org)}
                    >
                      Ndiyo, futa
                    </Button>
                    <Button
                      variant="ghost"
                      size="small"
                      onClick={() => setConfirmingDelete(null)}
                    >
                      Ghairi
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="mt-4 flex items-center gap-2 border-t border-surface-border pt-3">
                  <Link
                    href={`/organizations/${org.id}`}
                    className="inline-flex h-8 flex-1 items-center justify-center gap-1.5 rounded border border-surface-border bg-surface-panel px-3 text-caption font-medium text-ink-secondary transition-colors duration-150 hover:border-surface-border-strong hover:bg-surface-sunken"
                  >
                    Fungua
                    <Icon name="arrow-right" size={16} />
                  </Link>
                  {org.my_role === "owner" && (
                    <Button
                      variant="danger"
                      size="small"
                      icon="trash"
                      onClick={() => handleDelete(org)}
                      aria-label={`Futa shirika ${org.name}`}
                    />
                  )}
                </div>
              )}
            </Card>
          ))}

          {/*
            The prototype leads the grid with a dashed create tile rather than
            putting creation in the page header. Both are reachable here: this
            card is the in-grid affordance, and the header button stays because
            the form it opens is at the top of the page.
          */}
          <button
            type="button"
            onClick={() => {
              setShowForm(true);
              setError(null);
            }}
            className="flex min-h-[200px] flex-col items-center justify-center gap-2 rounded-xl border-[1.5px] border-dashed border-surface-border-strong bg-surface-panel text-ink-secondary transition-colors duration-200 ease-standard hover:border-primary-400 hover:bg-primary-50/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500"
          >
            <span className="grid h-11 w-11 place-items-center rounded-full bg-primary-50 text-primary-600">
              <Icon name="plus" size={20} />
            </span>
            <strong className="text-body font-semibold text-ink">
              Tengeneza shirika
            </strong>
            <small className="text-caption text-ink-muted">
              Anza na wanachama, miradi na data
            </small>
          </button>
        </div>
      )}
    </AppShell>
  );
}