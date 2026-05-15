"use client";

import type { RunCreateRequest, RunProfile } from "../../lib/api";

interface RunProfilesPanelProps {
  profiles: RunProfile[];
  profileName: string;
  profileDescription: string;
  selectedProfileId: number | null;
  isSaving: boolean;
  isLaunching: boolean;
  form: RunCreateRequest;
  onProfileNameChange: (value: string) => void;
  onProfileDescriptionChange: (value: string) => void;
  onSaveProfile: () => void;
  onUpdateProfile: () => void;
  onLoadProfile: (profile: RunProfile) => void;
  onLaunchProfile: (profileId: number) => void;
  onDeleteProfile: (profileId: number) => void;
  profileNameInputRef?: (node: HTMLInputElement | null) => void;
}

export default function RunProfilesPanel({
  profiles,
  profileName,
  profileDescription,
  selectedProfileId,
  isSaving,
  isLaunching,
  form,
  onProfileNameChange,
  onProfileDescriptionChange,
  onSaveProfile,
  onUpdateProfile,
  onLoadProfile,
  onLaunchProfile,
  onDeleteProfile,
  profileNameInputRef,
}: RunProfilesPanelProps) {
  return (
    <div className="panel grid" style={{ gap: 12 }}>
      <div>
        <h2 style={{ margin: "0 0 6px" }}>Saved Profiles</h2>
        <div className="muted">Save reusable run definitions, load them into the launch form, or launch them directly.</div>
      </div>
      <div className="grid two">
        <label>
          Profile Name
          <input ref={profileNameInputRef} value={profileName} onChange={(event) => onProfileNameChange(event.target.value)} placeholder="Daily Doctor - Jos Store" />
        </label>
        <label>
          Description
          <input
            value={profileDescription}
            onChange={(event) => onProfileDescriptionChange(event.target.value)}
            placeholder="Short operator note"
          />
        </label>
      </div>
      <div className="muted">Current launch form snapshot: {form.flow} · {form.timing} · {form.plan}</div>
      <div className="grid two">
        <button disabled={isSaving || !profileName.trim()} onClick={onSaveProfile}>
          {isSaving ? "Saving..." : "Save Current Form as Profile"}
        </button>
        <button className="secondary" disabled={isSaving || !selectedProfileId} onClick={onUpdateProfile}>
          {isSaving ? "Saving..." : "Update Selected Profile"}
        </button>
      </div>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Flow</th>
            <th>Store</th>
            <th>Phone</th>
            <th>Updated</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {profiles.length ? (
            profiles.map((profile) => {
              const isCatalogProfile = Boolean(profile.catalog_slug);
              return (
              <tr key={profile.id} style={selectedProfileId === profile.id ? { background: "var(--bg-tertiary)" } : undefined}>
                <td>
                  <div style={{ fontWeight: 600 }}>
                    {profile.name}
                    {profile.catalog_slug ? (
                      <span className="muted" style={{ marginLeft: 8, fontSize: "11px", fontWeight: 500 }}>
                        Catalog
                      </span>
                    ) : null}
                  </div>
                  {profile.description ? <div style={{ fontSize: "12px", opacity: 0.75 }}>{profile.description}</div> : null}
                </td>
                <td>{profile.flow}</td>
                <td>{profile.store_id || "auto"}</td>
                <td>{profile.phone || "auto"}</td>
                <td>{profile.updated_at}</td>
                <td>
                  <div className="row-actions">
                    <button className="secondary small" onClick={() => onLoadProfile(profile)}>Load</button>
                    <button className="small" disabled={isLaunching} onClick={() => onLaunchProfile(profile.id)}>
                      {isLaunching ? "Launching..." : "Launch"}
                    </button>
                    {!isCatalogProfile ? (
                      <button className="secondary small" onClick={() => onDeleteProfile(profile.id)}>Delete</button>
                    ) : null}
                  </div>
                </td>
              </tr>
            );
            })
          ) : (
            <tr>
              <td colSpan={6} className="muted" style={{ textAlign: "center", padding: "18px 12px" }}>
                No saved profiles yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
