"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { SelectInput, TextInput } from "@/components/Field";
import { Icon } from "@/components/Icon";
import { TableSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import {
  api,
  apiErrorMessage,
  OrgMember,
  OrgProject,
  OrgRole,
  OrgTeam,
  Organization,
  TeamMember,
} from "@/lib/api";

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

function memberLabel(person: { full_name: string | null; email: string | null }): string {
  return person.full_name ?? person.email ?? "Mwanachama";
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

type ConfirmTarget =
  | { kind: "member"; id: number; label: string }
  | { kind: "team-member"; id: number; label: string }
  | { kind: "project"; id: number; label: string }
  | { kind: "team"; id: number; label: string }
  | { kind: "org"; id: number; label: string };

type RenameTarget = { kind: "project" | "team"; id: number; name: string };

const CONFIRM_COPY: Record<ConfirmTarget["kind"], { question: string; warning: string }> = {
  member: {
    question: "Mtoe mwanachama huyu kwenye shirika?",
    warning: "Atapoteza ruhusa ya kufikia data ya shirika hili.",
  },
  "team-member": {
    question: "Mtoe mwanachama huyu kwenye timu?",
    warning: "Ataendelea kuwa mwanachama wa shirika.",
  },
  project: {
    question: "Futa mradi huu?",
    warning: "Data iliyowekwa ndani ya mradi itabaki, lakini haitaonekana tena.",
  },
  team: {
    question: "Futa timu hii?",
    warning: "Wanachama wa timu itabaki kwenye shirika.",
  },
  org: {
    question: "Futa shirika zima?",
    warning: "Hii itafuta wanachama, miradi, timu na data zote za shirika. Kitendo hiki hakiwezi kubatilishwa.",
  },
};

function isSameTarget(
  target: ConfirmTarget | null,
  kind: ConfirmTarget["kind"],
  id: number
): boolean {
  return target?.kind === kind && target.id === id;
}

function InlineConfirm({
  target,
  onCancel,
  onConfirm,
}: {
  target: ConfirmTarget;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const copy = CONFIRM_COPY[target.kind];
  return (
    <div
      role="alertdialog"
      aria-label={copy.question}
      className="w-full rounded-md border border-danger/30 bg-danger-bg p-3"
    >
      <p className="flex items-start gap-1.5 text-body font-medium text-danger-700">
        <Icon name="alert-triangle" size={15} className="mt-0.5 shrink-0" />
        {copy.question}
      </p>
      <p className="mt-1 text-caption text-danger-700">
        <span className="font-medium">{target.label}</span> — {copy.warning}
      </p>
      <div className="mt-2 flex items-center gap-2">
        <Button variant="danger" size="small" icon="trash" onClick={onConfirm}>
          Ndiyo, endelea
        </Button>
        <Button variant="ghost" size="small" onClick={onCancel}>
          Ghairi
        </Button>
      </div>
    </div>
  );
}

export default function OrganizationDetailPage() {
  const params = useParams<{ id: string }>();
  const organizationId = Number(params.id);
  const { showToast } = useToast();

  const [org, setOrg] = useState<Organization | null>(null);
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [projects, setProjects] = useState<OrgProject[]>([]);
  const [teams, setTeams] = useState<OrgTeam[]>([]);
  const [teamMembers, setTeamMembers] = useState<Record<number, TeamMember[]>>({});
  const [loading, setLoading] = useState(true);

  // create-org / add-member / create-project forms
  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState<OrgRole>("analyst");
  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [teamName, setTeamName] = useState("");
  const [teamDescription, setTeamDescription] = useState("");
  const [memberPicks, setMemberPicks] = useState<Record<number, number | "">>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [memberError, setMemberError] = useState<string | null>(null);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [teamError, setTeamError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<ConfirmTarget | null>(null);
  const [rename, setRename] = useState<RenameTarget | null>(null);

  const load = useCallback(async () => {
    try {
      const [organization, memberList, projectList, teamList] = await Promise.all([
        api.organizations.get(organizationId),
        api.organizations.members(organizationId),
        api.organizations.projects(organizationId),
        api.organizations.teams.list(organizationId),
      ]);
      setOrg(organization);
      setMembers(memberList);
      setProjects(projectList);
      setTeams(teamList);
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setLoading(false);
    }
  }, [organizationId, showToast]);

  const loadTeamMembers = useCallback(
    async (teamId: number) => {
      try {
        const list = await api.organizations.teams.members(organizationId, teamId);
        setTeamMembers((current) => ({ ...current, [teamId]: list }));
      } catch (caught) {
        showToast(apiErrorMessage(caught), "danger");
      }
    },
    [organizationId, showToast]
  );

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    teams.forEach((team) => {
      if (!teamMembers[team.id]) {
        loadTeamMembers(team.id);
      }
    });
  }, [teams, teamMembers, loadTeamMembers]);

  const myRole = org?.my_role ?? null;

  // --------------------------------------------------------- member actions

  async function handleAddMember(event: React.FormEvent) {
    event.preventDefault();
    const email = memberEmail.trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      setMemberError("Andika barua pepe sahihi, kwa mfano: mwanachama@example.com");
      return;
    }
    setBusy(true);
    setMemberError(null);
    try {
      await api.organizations.addMember(organizationId, { email, role: memberRole });
      showToast("Mwanachama ameongezwa", "success");
      setMemberEmail("");
      load();
    } catch (caught) {
      const message = apiErrorMessage(caught);
      setMemberError(message);
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
    const label = memberLabel(member);
    if (!isSameTarget(confirm, "member", member.user_id)) {
      setConfirm({ kind: "member", id: member.user_id, label });
      return;
    }
    setConfirm(null);
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
    if (projectName.trim().length < 2) {
      setProjectError("Jina la mradi linapaswa kuwa angalau herufi 2.");
      return;
    }
    setBusy(true);
    setProjectError(null);
    try {
      await api.organizations.createProject(organizationId, {
        name: projectName.trim(),
        description: projectDescription.trim() || undefined,
      });
      showToast("Mradi umetengenezwa", "success");
      setProjectName("");
      setProjectDescription("");
      load();
    } catch (caught) {
      const message = apiErrorMessage(caught);
      setProjectError(message);
      showToast(message, "danger");
    } finally {
      setBusy(false);
    }
  }

  async function handleRenameProject(project: OrgProject) {
    if (rename?.kind !== "project" || rename.id !== project.id) {
      setRename({ kind: "project", id: project.id, name: project.name });
      return;
    }
    const next = rename.name.trim();
    if (next.length < 2) {
      showToast("Jina la mradi haliachiwi tupu", "danger");
      return;
    }
    setRename(null);
    try {
      await api.organizations.updateProject(organizationId, project.id, { name: next });
      showToast("Mradi umesasishwa", "success");
      load();
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }

  async function handleDeleteProject(project: OrgProject) {
    if (!isSameTarget(confirm, "project", project.id)) {
      setConfirm({ kind: "project", id: project.id, label: project.name });
      return;
    }
    setConfirm(null);
    try {
      await api.organizations.removeProject(organizationId, project.id);
      showToast("Mradi umefutwa", "success");
      load();
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }

  // ----------------------------------------------------------- team actions

  async function handleCreateTeam(event: React.FormEvent) {
    event.preventDefault();
    if (teamName.trim().length < 2) {
      setTeamError("Jina la timu linapaswa kuwa angalau herufi 2.");
      return;
    }
    setBusy(true);
    setTeamError(null);
    try {
      await api.organizations.teams.create(organizationId, {
        name: teamName.trim(),
        description: teamDescription.trim() || undefined,
      });
      showToast("Timu imetengenezwa", "success");
      setTeamName("");
      setTeamDescription("");
      load();
    } catch (caught) {
      const message = apiErrorMessage(caught);
      setTeamError(message);
      showToast(message, "danger");
    } finally {
      setBusy(false);
    }
  }

  async function handleRenameTeam(team: OrgTeam) {
    if (rename?.kind !== "team" || rename.id !== team.id) {
      setRename({ kind: "team", id: team.id, name: team.name });
      return;
    }
    const next = rename.name.trim();
    if (next.length < 2) {
      showToast("Jina la timu haliachiwi tupu", "danger");
      return;
    }
    setRename(null);
    try {
      await api.organizations.teams.update(organizationId, team.id, { name: next });
      showToast("Timu imesasishwa", "success");
      load();
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }

  async function handleDeleteTeam(team: OrgTeam) {
    if (!isSameTarget(confirm, "team", team.id)) {
      setConfirm({ kind: "team", id: team.id, label: team.name });
      return;
    }
    setConfirm(null);
    try {
      await api.organizations.teams.remove(organizationId, team.id);
      showToast("Timu imefutwa", "success");
      load();
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }

  async function handleAddTeamMember(team: OrgTeam) {
    const pick = memberPicks[team.id];
    if (!pick) {
      showToast("Chagua mwanachama kwanza", "danger");
      return;
    }
    try {
      await api.organizations.teams.addMember(organizationId, team.id, pick);
      showToast("Mwanachama ameongezwa kwenye timu", "success");
      setMemberPicks((current) => ({ ...current, [team.id]: "" }));
      loadTeamMembers(team.id);
      load();
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }

  async function handleRemoveTeamMember(team: OrgTeam, member: TeamMember) {
    const label = memberLabel(member);
    if (!isSameTarget(confirm, "team-member", member.user_id)) {
      setConfirm({ kind: "member", id: member.user_id, label });
      return;
    }
    setConfirm(null);
    try {
      await api.organizations.teams.removeMember(organizationId, team.id, member.user_id);
      showToast("Mwanachama ameondolewa kwenye timu", "success");
      loadTeamMembers(team.id);
      load();
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }

  async function handleDeleteOrganization() {
    if (!org || org.my_role !== "owner") return;
    if (!isSameTarget(confirm, "org", org.id)) {
      setConfirm({ kind: "org", id: org.id, label: org.name });
      return;
    }
    setConfirm(null);
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
        <EmptyState
          title="Shirika halipo"
          description="Halijapatikana au huna ruhusa ya kuliona."
          icon="building"
        />
      </AppShell>
    );
  }

  return (
    <AppShell
      title={org.name}
      description={`@${org.slug}${org.description ? ` — ${org.description}` : ""}`}
      actions={
        org.my_role === "owner" &&
        (isSameTarget(confirm, "org", org.id) ? (
          <Button variant="secondary" onClick={() => setConfirm(null)}>
            Ghairi futa
          </Button>
        ) : (
          <Button variant="danger" icon="trash" onClick={handleDeleteOrganization}>
            Futa shirika
          </Button>
        ))
      }
    >
      {isSameTarget(confirm, "org", org.id) && (
        <InlineConfirm
          target={confirm!}
          onCancel={() => setConfirm(null)}
          onConfirm={handleDeleteOrganization}
        />
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        {[
          { label: "Wanachama", value: members.length, icon: "users" as const },
          { label: "Miradi", value: projects.length, icon: "folder" as const },
          { label: "Timu", value: teams.length, icon: "layers" as const },
        ].map((item) => (
          <div
            key={item.label}
            className="flex items-center gap-3 rounded-md border border-surface-border bg-surface-panel px-4 py-3"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-md bg-primary-50 text-primary-600">
              <Icon name={item.icon} size={18} />
            </span>
            <div>
              <p className="tabular font-mono text-h2 text-ink">{item.value}</p>
              <p className="text-caption text-ink-muted">{item.label}</p>
            </div>
          </div>
        ))}
      </div>

      {myRole && (
        <p className="flex flex-wrap items-center gap-2 text-caption text-ink-muted">
          Kiwango chako katika shirika hili:
          <Badge tone={ROLE_TONE[myRole]}>{ROLE_LABEL[myRole]}</Badge>
        </p>
      )}

      <Card
        title="Wanachama"
        description="Kila mwanachama ana kiwango: mwenyekiti, msimamizi, mchambuzi au mtazamaji."
        icon="users"
        actions={
          canManageMembers(myRole) && (
            <a
              href="#add-member"
              className="inline-flex h-9 items-center gap-1.5 rounded border border-surface-border bg-surface-panel px-3 text-caption font-medium text-ink-secondary transition-colors duration-150 hover:bg-surface-sunken"
            >
              <Icon name="plus" size={16} />
              Ongeza mwanachama
            </a>
          )
        }
      >
        <ul className="divide-y divide-surface-border">
          {members.map((member) => (
            <li key={member.id} className="py-3">
              {isSameTarget(confirm, "member", member.user_id) ? (
                <InlineConfirm
                  target={confirm!}
                  onCancel={() => setConfirm(null)}
                  onConfirm={() => handleRemoveMember(member)}
                />
              ) : (
                <div className="flex flex-wrap items-center gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary-100 text-primary-700">
                    <span className="text-body font-medium">{initials(member.full_name)}</span>
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-body text-ink">
                      {memberLabel(member)}
                      {member.role === "owner" && (
                        <span className="sr-only">, mwenyekiti</span>
                      )}
                    </p>
                    <p className="truncate text-caption text-ink-muted">{member.email}</p>
                  </div>
                  {canChangeMember(myRole, member.role) ? (
                    <div className="flex items-center gap-2">
                      <label className="sr-only" htmlFor={`role-${member.user_id}`}>
                        Kiwango cha {memberLabel(member)}
                      </label>
                      <select
                        id={`role-${member.user_id}`}
                        value={member.role}
                        onChange={(event) =>
                          handleChangeRole(member, event.target.value as OrgRole)
                        }
                        className="control h-9 w-auto py-0 text-caption"
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
                      <Button
                        variant="ghost"
                        size="small"
                        icon="trash"
                        onClick={() => handleRemoveMember(member)}
                        aria-label={`Mtoe ${memberLabel(member)}`}
                      />
                    </div>
                  ) : (
                    <Badge tone={ROLE_TONE[member.role as OrgRole] ?? "neutral"}>
                      {ROLE_LABEL[member.role as OrgRole] ?? member.role}
                    </Badge>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>

        {canManageMembers(myRole) && (
          <form
            id="add-member"
            onSubmit={handleAddMember}
            className="mt-4 flex flex-wrap items-end gap-3 rounded-md border border-surface-border bg-surface-sunken p-4"
          >
            <div className="min-w-[220px] flex-1">
              <TextInput
                id="member_email"
                label="Barua pepe ya mwanachama"
                type="email"
                required
                value={memberEmail}
                error={memberError ?? undefined}
                onChange={(event) => {
                  setMemberEmail(event.target.value);
                  if (memberError) setMemberError(null);
                }}
                placeholder="mwanachama@example.com"
              />
            </div>
            <div className="min-w-[160px]">
              <SelectInput
                id="member_role"
                label="Kiwango"
                value={memberRole}
                onChange={(event) => setMemberRole(event.target.value as OrgRole)}
                options={[
                  { value: "owner", label: "Mwenyekiti" },
                  { value: "admin", label: "Msimamizi" },
                  { value: "analyst", label: "Mchambuzi" },
                  { value: "viewer", label: "Mtazamaji" },
                ]}
              />
            </div>
            <Button type="submit" loading={busy} icon="plus">
              Ongeza
            </Button>
          </form>
        )}
      </Card>

      <Card
        title="Miradi"
        description="Miradi ni mapipa ya kufanyia kazi — data zinaweza kuwekwa ndani ya mradi kwenye siku zijazo."
        icon="folder"
      >
        {!canCreateProject(myRole) ? (
          <p className="text-body text-ink-secondary">
            Kiwango cha{" "}
            <Badge tone={ROLE_TONE["viewer"]}>Mtazamaji</Badge> hakiruhusu kuunda
            miradi. Muulize msimamizi au mwenyekiti akupe kiwango cha mchambuzi.
          </p>
        ) : (
          <form
            onSubmit={handleCreateProject}
            className="mb-4 flex flex-wrap items-end gap-3 rounded-md border border-surface-border bg-surface-sunken p-4"
          >
            <div className="min-w-[220px] flex-1">
              <TextInput
                id="project_name"
                label="Jina la mradi"
                required
                minLength={2}
                value={projectName}
                error={projectError ?? undefined}
                onChange={(event) => {
                  setProjectName(event.target.value);
                  if (projectError) setProjectError(null);
                }}
                placeholder="Mfano: Mauzo 2026"
              />
            </div>
            <div className="min-w-[220px] flex-1">
              <TextInput
                id="project_desc"
                label="Maelezo"
                optionalLabel="hiari"
                value={projectDescription}
                onChange={(event) => setProjectDescription(event.target.value)}
                placeholder="Mradi huu una data gani?"
              />
            </div>
            <Button type="submit" loading={busy} icon="plus">
              Unda mradi
            </Button>
          </form>
        )}

        {projects.length === 0 ? (
          <EmptyState
            title="Hakuna miradi bado"
            description="Unda mradi wa kwanza na uanze kupanga kazi za uchambuzi."
            icon="folder"
          />
        ) : (
          <ul className="divide-y divide-surface-border">
            {projects.map((project) => (
              <li key={project.id} className="py-3">
                {isSameTarget(confirm, "project", project.id) ? (
                  <InlineConfirm
                    target={confirm!}
                    onCancel={() => setConfirm(null)}
                    onConfirm={() => handleDeleteProject(project)}
                  />
                ) : rename?.kind === "project" && rename.id === project.id ? (
                  <form
                    className="flex flex-wrap items-end gap-2"
                    onSubmit={(event) => {
                      event.preventDefault();
                      handleRenameProject(project);
                    }}
                  >
                    <div className="min-w-[220px] flex-1">
                      <TextInput
                        id={`rename-project-${project.id}`}
                        label="Jina jipya la mradi"
                        value={rename.name}
                        onChange={(event) =>
                          setRename({ ...rename, name: event.target.value })
                        }
                      />
                    </div>
                    <Button type="submit" size="small" icon="check">
                      Hifadhi
                    </Button>
                    <Button
                      variant="ghost"
                      size="small"
                      onClick={() => setRename(null)}
                    >
                      Ghairi
                    </Button>
                  </form>
                ) : (
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-surface-sunken text-ink-secondary">
                      <Icon name="folder" size={18} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-body text-ink">{project.name}</p>
                      <p className="truncate text-caption text-ink-muted">
                        {project.description ?? "Hakuna maelezo"}
                      </p>
                    </div>
                    <Badge tone="info" icon="database">
                      {project.dataset_count}{" "}
                      {project.dataset_count === 1 ? "dataset" : "datasets"}
                    </Badge>
                    {canManageProject(myRole) && (
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="small"
                          icon="sliders"
                          onClick={() => handleRenameProject(project)}
                          aria-label={`Badilisha jina la ${project.name}`}
                        />
                        <Button
                          variant="ghost"
                          size="small"
                          icon="trash"
                          onClick={() => handleDeleteProject(project)}
                          aria-label={`Futa mradi ${project.name}`}
                        />
                      </div>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card
        title="Timu"
        description="Timu zinakusanya wanachama ili kushiriki kazi. Kiwango cha mwanachama kwenye shirika ndio kinachodhibiti ruhusa yake."
        icon="layers"
      >
        {!canCreateProject(myRole) ? (
          <p className="text-body text-ink-secondary">
            Kiwango cha{" "}
            <Badge tone={ROLE_TONE["viewer"]}>Mtazamaji</Badge> hakiruhusu kutengeneza
            timu. Muulize msimamizi au mwenyekiti akupe kiwango cha mchambuzi.
          </p>
        ) : (
          <form
            onSubmit={handleCreateTeam}
            className="mb-4 flex flex-wrap items-end gap-3 rounded-md border border-surface-border bg-surface-sunken p-4"
          >
            <div className="min-w-[220px] flex-1">
              <TextInput
                id="team_name"
                label="Jina la timu"
                required
                minLength={2}
                value={teamName}
                error={teamError ?? undefined}
                onChange={(event) => {
                  setTeamName(event.target.value);
                  if (teamError) setTeamError(null);
                }}
                placeholder="Mfano: Timu ya Uchambuzi"
              />
            </div>
            <div className="min-w-[220px] flex-1">
              <TextInput
                id="team_desc"
                label="Maelezo"
                optionalLabel="hiari"
                value={teamDescription}
                onChange={(event) => setTeamDescription(event.target.value)}
                placeholder="Timu hii inafanya nini?"
              />
            </div>
            <Button type="submit" loading={busy} icon="plus">
              Unda timu
            </Button>
          </form>
        )}

        {teams.length === 0 ? (
          <EmptyState
            title="Hakuna timu bado"
            description="Tengeneza timu ya kwanza kwa kupanua wanachama kwenye kazi moja."
            icon="layers"
          />
        ) : (
          <ul className="divide-y divide-surface-border">
            {teams.map((team) => {
              const currentMembers = teamMembers[team.id] ?? [];
              const taken = new Set(currentMembers.map((member) => member.user_id));
              const available = members.filter((member) => !taken.has(member.user_id));
              return (
                <li key={team.id} className="py-4">
                  {isSameTarget(confirm, "team", team.id) ? (
                    <InlineConfirm
                      target={confirm!}
                      onCancel={() => setConfirm(null)}
                      onConfirm={() => handleDeleteTeam(team)}
                    />
                  ) : rename?.kind === "team" && rename.id === team.id ? (
                    <form
                      className="flex flex-wrap items-end gap-2"
                      onSubmit={(event) => {
                        event.preventDefault();
                        handleRenameTeam(team);
                      }}
                    >
                      <div className="min-w-[220px] flex-1">
                        <TextInput
                          id={`rename-team-${team.id}`}
                          label="Jina jipya la timu"
                          value={rename.name}
                          onChange={(event) =>
                            setRename({ ...rename, name: event.target.value })
                          }
                        />
                      </div>
                      <Button type="submit" size="small" icon="check">
                        Hifadhi
                      </Button>
                      <Button
                        variant="ghost"
                        size="small"
                        onClick={() => setRename(null)}
                      >
                        Ghairi
                      </Button>
                    </form>
                  ) : (
                    <>
                      <div className="flex flex-wrap items-center gap-3">
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-surface-sunken text-ink-secondary">
                          <Icon name="users" size={18} />
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-body text-ink">{team.name}</p>
                          <p className="truncate text-caption text-ink-muted">
                            {team.description ?? "Hakuna maelezo"}
                          </p>
                        </div>
                        <Badge tone="info" icon="users">
                          {team.member_count}{" "}
                          {team.member_count === 1 ? "mwanachama" : "wanachama"}
                        </Badge>
                        {canManageProject(myRole) && (
                          <div className="flex items-center gap-1">
                            <Button
                              variant="ghost"
                              size="small"
                              icon="sliders"
                              onClick={() => handleRenameTeam(team)}
                              aria-label={`Badilisha jina la ${team.name}`}
                            />
                            <Button
                              variant="ghost"
                              size="small"
                              icon="trash"
                              onClick={() => handleDeleteTeam(team)}
                              aria-label={`Futa timu ${team.name}`}
                            />
                          </div>
                        )}
                      </div>

                      <ul className="mt-3 space-y-2 pl-12">
                        {currentMembers.length === 0 && (
                          <li className="text-caption text-ink-muted">
                            Hakuna mwanachama kwenye timu hii bado.
                          </li>
                        )}
                        {currentMembers.map((member) => (
                          <li key={member.id} className="py-1">
                            {isSameTarget(confirm, "team-member", member.user_id) ? (
                              <InlineConfirm
                                target={confirm!}
                                onCancel={() => setConfirm(null)}
                                onConfirm={() => handleRemoveTeamMember(team, member)}
                              />
                            ) : (
                              <div className="flex flex-wrap items-center gap-3 text-body">
                                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary-100 text-primary-700">
                                  <span className="text-caption font-medium">
                                    {initials(member.full_name)}
                                  </span>
                                </span>
                                <span className="min-w-0 flex-1 truncate">
                                  {memberLabel(member)}
                                </span>
                                {canManageProject(myRole) && (
                                  <Button
                                    variant="ghost"
                                    size="small"
                                    icon="trash"
                                    onClick={() => handleRemoveTeamMember(team, member)}
                                    aria-label={`Mtoe ${memberLabel(member)} kwenye ${team.name}`}
                                  />
                                )}
                              </div>
                            )}
                          </li>
                        ))}
                      </ul>

                      {canManageProject(myRole) && available.length > 0 && (
                        <div className="mt-3 flex flex-wrap items-end gap-3 pl-12">
                          <div className="min-w-[200px]">
                            <SelectInput
                              id={`team-member-${team.id}`}
                              label="Ongeza mwanachama"
                              value={
                                memberPicks[team.id] === undefined
                                  ? ""
                                  : String(memberPicks[team.id])
                              }
                              onChange={(event) =>
                                setMemberPicks((current) => ({
                                  ...current,
                                  [team.id]: event.target.value
                                    ? Number(event.target.value)
                                    : "",
                                }))
                              }
                              options={[
                                { value: "", label: "Chagua mwanachama" },
                                ...available.map((member) => ({
                                  value: String(member.user_id),
                                  label: memberLabel(member),
                                })),
                              ]}
                            />
                          </div>
                          <Button
                            size="small"
                            icon="plus"
                            onClick={() => handleAddTeamMember(team)}
                          >
                            Ongeza
                          </Button>
                        </div>
                      )}
                    </>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </AppShell>
  );
}


