"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { Icon } from "@/components/Icon";
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
    setBusy(true);
    setError(null);
    try {
      const org = await api.organizations.create({ name, description });
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
    if (!window.confirm(`Futa shirika "${org.name}" na data yake yote?`)) return;
    try {
      await api.organizations.remove(org.id);
      showToast("Shirika limefutwa", "success");
      load();
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }

  return (
    <AppShell
      title="Mashirika"
      description="Panga watu na data kwenye mashirika, na kila mwanachama apate kiwango chake cha ruhusa."
      actions={
        <Button onClick={() => setShowForm((value) => !value)}>
          <Icon name="plus" size={18} />
          Shirika jipya
        </Button>
      }
    >
      {showForm && (
        <Card
          title="Tengeneza shirika"
          description="Wewe utakuwa mwenyekiti (owner) wa shirika hili."
        >
          <form onSubmit={handleCreate} className="space-y-4">
            <div>
              <label htmlFor="org_name" className="block text-body text-neutral-900">
                Jina la shirika
              </label>
              <input
                id="org_name"
                required
                minLength={2}
                value={name}
                onChange={(event) => setName(event.target.value)}
                className="mt-1 h-10 w-full rounded border border-neutral-200 px-3 text-body outline-none focus:border-primary-500"
                placeholder="Mfano: Shule ya Taifa"
              />
            </div>
            <div>
              <label htmlFor="org_desc" className="block text-body text-neutral-900">
                Maelezo (hiari)
              </label>
              <textarea
                id="org_desc"
                rows={2}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                className="mt-1 w-full rounded border border-neutral-200 px-3 py-2 text-body outline-none focus:border-primary-500"
                placeholder="Shirika hili litachambua data gani?"
              />
            </div>
            {error && <p className="text-body text-danger">{error}</p>}
            <div className="flex items-center gap-2">
              <Button type="submit" loading={busy}>
                Tengeneza
              </Button>
              <Button variant="ghost" onClick={() => setShowForm(false)}>
                Ghairi
              </Button>
            </div>
          </form>
        </Card>
      )}

      {loading ? (
        <TableSkeleton rows={3} />
      ) : organizations.length === 0 ? (
        <EmptyState
          title="Huna mashirika bado"
          description="Shirika hukusanya wanachama, miradi na data pamoja chini ya sheria zile zile."
          action={
            <Button onClick={() => setShowForm(true)}>
              <Icon name="building" size={18} />
              Tengeneza la kwanza
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {organizations.map((org) => (
            <Card key={org.id} className="flex flex-col">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded bg-primary-100 text-primary-700">
                    <Icon name="building" size={20} />
                  </span>
                  <div>
                    <Link
                      href={`/organizations/${org.id}`}
                      className="block text-h3 text-neutral-900 hover:text-primary-700"
                    >
                      {org.name}
                    </Link>
                    <p className="text-caption text-neutral-600">@{org.slug}</p>
                  </div>
                </div>
                {org.my_role && <RoleBadge role={org.my_role} />}
              </div>

              {org.description && (
                <p className="mt-3 text-body text-neutral-600">{org.description}</p>
              )}

              <div className="mt-4 flex items-center gap-4 text-body text-neutral-600">
                <span className="inline-flex items-center gap-1.5">
                  <Icon name="users" size={16} className="text-neutral-400" />
                  {org.member_count} wanachama
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Icon name="folder" size={16} className="text-neutral-400" />
                  {org.project_count} miradi
                </span>
              </div>

              <div className="mt-4 flex items-center gap-2 border-t border-neutral-200 pt-3">
                <Link
                  href={`/organizations/${org.id}`}
                  className="inline-flex h-8 flex-1 items-center justify-center gap-1.5 rounded border border-neutral-200 bg-white px-3 text-[13px] font-medium text-neutral-600 transition-colors duration-150 hover:bg-neutral-100"
                >
                  Fungua
                  <Icon name="arrow-right" size={16} />
                </Link>
                {org.my_role === "owner" && (
                  <Button
                    variant="danger"
                    size="small"
                    onClick={() => handleDelete(org)}
                    aria-label={`Futa shirika ${org.name}`}
                  >
                    <Icon name="trash" size={16} />
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </AppShell>
  );
}