"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { Icon } from "@/components/Icon";
import { TableSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import { api, apiErrorMessage, OrgMember, OrgProject, Organization, OrgRole } from "@/lib/api";

const ROLE_LABEL: Record<OrgRole, string> = {
  owner: "Mwenyekiti",
  admin: "Msimamizi",
  analyst: "Mchambuzi",
  viewer: "Mtazamaji",
};

const ROLE_TONE: Record<OrgRole, "primary" | "success" | "info" | "neutral"> = {
  owner: "primary",
  admin: "success",
  analyst: "info",
  viewer: "neutral",
};

function initials(name: string | null): string {
  const parts = (name ?? "?").trim().split(/\s+/);
  return (parts[0]?.[0] ?? "?").toUpperCase() + (parts[1]?.[0] ?? "").toUpperCase();
}

// ------------------------------------------------------------- permissions

function canManageMembers(role: OrgRole | null): boolean {
  return role === "owner" || role === "admin";
}

function canChangeMember(role: OrgRole | null, memberRole: string): boolean {
  if (role === "owner" && memberRole !== "owner") return true;
  if (role === "admin" && (memberRole === "analyst" || memberRole === "viewer")) {
    return true;
  }
  return false;
}

function canCreateProject(role: OrgRole | null): boolean {
  return role === "owner" || role === "admin" || role === "analyst";
}

function canManageProject(role: OrgRole | null): boolean {
  return role === "owner" || role === "admin";
}

export default function OrganizationDetailPage() {
  const params = useParams<{ id: string }>();
  const organizationId = Number(params.id);
  const { showToast } = useToast();

  const [org, setOrg] = useState<Organization | null>(null);
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [projects, setProjects] = useState<OrgProject[]>([]);
  const [loading, setLoading] = useState(true);

  // create-org / add-member / create-project forms
  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState<OrgRole>("analyst");
  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [organization, memberList, projectList] = await Promise.all([
        api.organizations.get(organizationId),
        api.organizations.members(organizationId),
        api.organizations.projects(organizationId),
      ]);
      setOrg(organization);
      setMembers(memberList);
      setProjects(projectList);
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setLoading(false);
    }
  }, [organizationId, showToast]);

  useEffect(() => {
    load();
  }, [load]);

  const myRole = org?.my_role ?? null;

  // --------------------------------------------------------- member actions

  async function handleAddMember(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.organizations.addMember(organizationId, {
        email: memberEmail,
        role: memberRole,
      });
      showToast("Mwanachama ameongezwa", "success");
      setMemberEmail("");
      load();
    } catch (caught) {
      const message = apiErrorMessage(caught);
      setError(message);
      showToast(message, "danger");
    } finally {
      setBusy(false);
    }
  }

  async function handleChangeRole(member: OrgMember, role: OrgRole) {
    try {
      await api.organizations.updateMember(organizationId, member.user_id, { role });
      showToast("Kiwango kimebadilishwa", "success");
      load();
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
      load();
    }
  }

  async function handleRemoveMember(member: OrgMember) {
    if (!window.confirm(`Mtoe "${member.full_name ?? member.email}" kwenye shirika?`)) {
      return;
    }
    try {
      await api.organizations.removeMember(organizationId, member.user_id);
      showToast("Mwanachama ameondolewa", "success");
      load();
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }

  // --------------------------------------------------------- project actions

  async function handleCreateProject(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.organizations.createProject(organizationId, {
        name: projectName,
        description: projectDescription,
      });
      showToast("Mradi umetengenezwa", "success");
      setProjectName("");
      setProjectDescription("");
      load();
    } catch (caught) {
      const message = apiErrorMessage(caught);
      setError(message);
      showToast(message, "danger");
    } finally {
      setBusy(false);
    }
  }

  async function handleRenameProject(project: OrgProject) {
    const name = window.prompt("Jina jipya la mradi:", project.name);
    if (name === null) return;
    if (name.trim() === "") {
      showToast("Jina la mradi haliachiwi tupu", "danger");
      return;
    }
    try {
      await api.organizations.updateProject(organizationId, project.id, {
        name: name.trim(),
      });
      showToast("Mradi umesasishwa", "success");
      load();
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }

  async function handleDeleteProject(project: OrgProject) {
    if (!window.confirm(`Futa mradi "${project.name}"?`)) return;
    try {
      await api.organizations.removeProject(organizationId, project.id);
      showToast("Mradi umefutwa", "success");
      load();
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }

  async function handleDeleteOrganization() {
    if (!org || org.my_role !== "owner") return;
    if (
      !window.confirm(
        `Futa shirika zima "${org.name}"? Hii itafuta wanachama na miradi.`
      )
    )
      return;
    try {
      await api.organizations.remove(organizationId);
      showToast("Shirika limefutwa", "success");
      window.location.href = "/organizations";
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }

  if (loading) {
    return (
      <AppShell title="Shirika">
        <TableSkeleton rows={4} />
      </AppShell>
    );
  }

  if (!org) {
    return (
      <AppShell title="Shirika">
        <EmptyState title="Shirika halipo" description="Halijapatikana au huna ruhusa ya kuliona." />
      </AppShell>
    );
  }

  return (
    <AppShell
      title={org.name}
      description={`@${org.slug}${org.description ? ` — ${org.description}` : ""}`}
      actions={
        org.my_role === "owner" && (
          <Button variant="danger" onClick={handleDeleteOrganization}>
            <Icon name="trash" size={18} />
            Futa shirika
          </Button>
        )
      }
    >
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-3 rounded border border-neutral-200 bg-white px-4 py-3">
          <Icon name="users" size={20} className="text-primary-600" />
          <div>
            <p className="text-h2">{members.length}</p>
            <p className="text-caption text-neutral-600">Wanachama</p>
          </div>
        </div>
        <div className="flex items-center gap-3 rounded border border-neutral-200 bg-white px-4 py-3">
          <Icon name="folder" size={20} className="text-primary-600" />
          <div>
            <p className="text-h2">{projects.length}</p>
            <p className="text-caption text-neutral-600">Miradi</p>
          </div>
        </div>
        {myRole && (
          <Badge tone={ROLE_TONE[myRole]} className="px-3 py-1">
            {ROLE_LABEL[myRole]}
          </Badge>
        )}
      </div>

      <Card
        title="Wanachama"
        description="Kila mwanachama ana kiwango: mwenyekiti, msimamizi, mchambuzi au mtazamaji."
        actions={
          canManageMembers(myRole) && (
            <Link
              href="#add-member"
              className="inline-flex h-10 items-center gap-2 rounded bg-primary-600 px-4 text-body font-medium text-white transition-colors duration-150 hover:bg-primary-700"
            >
              <Icon name="plus" size={18} />
              Ongeza mwanachama
            </Link>
          )
        }
      >
        <ul className="divide-y divide-neutral-200">
          {members.map((member) => (
            <li key={member.id} className="flex flex-wrap items-center gap-3 py-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary-100 text-primary-700">
                <span className="text-body font-medium">{initials(member.full_name)}</span>
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-body text-neutral-900">
                  {member.full_name ?? member.email}
                  {member.role === "owner" && (
                    <span className="sr-only">, mwenyekiti</span>
                  )}
                </p>
                <p className="truncate text-caption text-neutral-600">{member.email}</p>
              </div>
              {canChangeMember(myRole, member.role) ? (
                <>
                  <label className="sr-only" htmlFor={`role-${member.user_id}`}>
                    Kiwango cha {member.full_name ?? member.email}
                  </label>
                  <select
                    id={`role-${member.user_id}`}
                    value={member.role}
                    onChange={(event) =>
                      handleChangeRole(member, event.target.value as OrgRole)
                    }
                    className="h-9 rounded border border-neutral-200 bg-white px-2 text-body outline-none focus:border-primary-500"
                  >
                  <option value="analyst">Mchambuzi</option>
                  <option value="viewer">Mtazamaji</option>
                  {myRole === "owner" && (
                    <>
                      <option value="admin">Msimamizi</option>
                      <option value="owner">Mwenyekiti</option>
                    </>
                  )}
                </select>
                </>
              ) : (
                <Badge tone={ROLE_TONE[member.role as OrgRole] ?? "neutral"}>
                  {ROLE_LABEL[member.role as OrgRole] ?? member.role}
                </Badge>
              )}
              {canChangeMember(myRole, member.role) && (
                <Button
                  variant="ghost"
                  size="small"
                  onClick={() => handleRemoveMember(member)}
                  aria-label={`Mtoe ${member.full_name ?? member.email}`}
                >
                  <Icon name="trash" size={16} />
                </Button>
              )}
            </li>
          ))}
        </ul>

        {canManageMembers(myRole) && (
          <form
            id="add-member"
            onSubmit={handleAddMember}
            className="mt-4 flex flex-wrap items-end gap-3 rounded border border-neutral-200 bg-neutral-50 p-4"
          >
            <div className="min-w-[220px] flex-1">
              <label htmlFor="member_email" className="block text-body text-neutral-900">
                Barua pepe ya mwanachama
              </label>
              <input
                id="member_email"
                type="email"
                required
                value={memberEmail}
                onChange={(event) => setMemberEmail(event.target.value)}
                className="mt-1 h-10 w-full rounded border border-neutral-200 bg-white px-3 text-body outline-none focus:border-primary-500"
                placeholder="mwanachama@example.com"
              />
            </div>
            <div>
              <label htmlFor="member_role" className="block text-body text-neutral-900">
                Kiwango
              </label>
              <select
                id="member_role"
                value={memberRole}
                onChange={(event) => setMemberRole(event.target.value as OrgRole)}
                className="mt-1 h-10 rounded border border-neutral-200 bg-white px-3 text-body outline-none focus:border-primary-500"
              >
                <option value="owner">Mwenyekiti</option>
                <option value="admin">Msimamizi</option>
                <option value="analyst">Mchambuzi</option>
                <option value="viewer">Mtazamaji</option>
              </select>
            </div>
            <Button type="submit" loading={busy}>
              Ongeza
            </Button>
            {error && <p className="w-full text-body text-danger">{error}</p>}
          </form>
        )}
      </Card>

      <Card
        title="Miradi"
        description="Miradi ni mapipa ya kufanyia kazi — data zinaweza kuwekwa ndani ya mradi kwenye siku zijazo."
      >
        {!canCreateProject(myRole) ? (
          <p className="text-body text-neutral-600">
            Kiwango cha{" "}
            <Badge tone={ROLE_TONE["viewer"]}>Mtazamaji</Badge> hakiruhusu kuunda
            miradi. Muulize msimamizi au mwenyekiti akupe kiwango cha mchambuzi.
          </p>
        ) : (
          <form
            onSubmit={handleCreateProject}
            className="mb-4 flex flex-wrap items-end gap-3 rounded border border-neutral-200 bg-neutral-50 p-4"
          >
            <div className="min-w-[220px] flex-1">
              <label htmlFor="project_name" className="block text-body text-neutral-900">
                Jina la mradi
              </label>
              <input
                id="project_name"
                required
                minLength={2}
                value={projectName}
                onChange={(event) => setProjectName(event.target.value)}
                className="mt-1 h-10 w-full rounded border border-neutral-200 bg-white px-3 text-body outline-none focus:border-primary-500"
                placeholder="Mfano: Mauzo 2026"
              />
            </div>
            <div className="min-w-[220px] flex-1">
              <label htmlFor="project_desc" className="block text-body text-neutral-900">
                Maelezo (hiari)
              </label>
              <input
                id="project_desc"
                value={projectDescription}
                onChange={(event) => setProjectDescription(event.target.value)}
                className="mt-1 h-10 w-full rounded border border-neutral-200 bg-white px-3 text-body outline-none focus:border-primary-500"
                placeholder="Mradi huu una data gani?"
              />
            </div>
            <Button type="submit">Unda mradi</Button>
          </form>
        )}

        {projects.length === 0 ? (
          <EmptyState
            title="Hakuna miradi bado"
            description="Unda mradi wa kwanza na uanze kupanga kazi za uchambuzi."
          />
        ) : (
          <ul className="divide-y divide-neutral-200">
            {projects.map((project) => (
              <li key={project.id} className="flex flex-wrap items-center gap-3 py-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded bg-neutral-100 text-neutral-600">
                  <Icon name="folder" size={18} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-body text-neutral-900">{project.name}</p>
                  <p className="truncate text-caption text-neutral-600">
                    {project.description ?? "Hakuna maelezo"}
                  </p>
                </div>
                <Badge tone="info">
                  {project.dataset_count} {project.dataset_count === 1 ? "dataset" : "datasets"}
                </Badge>
                {canManageProject(myRole) && (
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="small"
                      onClick={() => handleRenameProject(project)}
                      aria-label={`Badilisha jina la ${project.name}`}
                    >
                      <Icon name="sliders" size={16} />
                    </Button>
                    <Button
                      variant="ghost"
                      size="small"
                      onClick={() => handleDeleteProject(project)}
                      aria-label={`Futa mradi ${project.name}`}
                    >
                      <Icon name="trash" size={16} />
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </AppShell>
  );
}