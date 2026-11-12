import { useEffect, useState } from "react";
import { api, assetFileUrl } from "../api";
import type { Profile } from "../types";
import { CATEGORY_LABELS } from "../types";

const CATEGORIES = ["face", "skin", "body"] as const;

export default function ProfilesPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const refresh = () => {
    api
      .listProfiles()
      .then(setProfiles)
      .catch((err: Error) => setError(err.message));
  };

  useEffect(refresh, []);

  const createProfile = async () => {
    if (!name.trim()) return;
    setError(null);
    try {
      await api.createProfile(name.trim(), notes.trim() || undefined);
      setName("");
      setNotes("");
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const uploadReference = async (
    profileId: number,
    category: string,
    file: File | undefined,
  ) => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await api.uploadReference(profileId, category, file);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  };

  return (
    <>
      <h2>Perfiles de modelo</h2>
      <p className="muted">
        Cada perfil conserva referencias visuales persistentes: rostro, piel y cuerpo.
        Las referencias se reutilizan entre proyectos y generaciones.
      </p>

      <section className="card">
        <h3>Nuevo perfil</h3>
        <label htmlFor="profile-name">Nombre</label>
        <input
          id="profile-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Ej. Modelo 1"
        />
        <label htmlFor="profile-notes">Notas</label>
        <input
          id="profile-notes"
          type="text"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Rasgos, contexto, observaciones…"
        />
        <button className="primary" onClick={createProfile}>
          Crear perfil
        </button>
      </section>

      {error && <div className="error">{error}</div>}

      <div className="grid">
        {profiles.map((profile) => (
          <section className="card" key={profile.id}>
            <h3>{profile.name}</h3>
            {profile.notes && <p className="muted">{profile.notes}</p>}
            {CATEGORIES.map((category) => {
              const refs = profile.references.filter(
                (ref) => ref.category === category,
              );
              return (
                <div key={category}>
                  <label>
                    {CATEGORY_LABELS[category]} ({refs.length})
                  </label>
                  <div className="thumbs">
                    {refs.map((ref) => (
                      <img
                        key={ref.id}
                        src={assetFileUrl(ref.asset_id)}
                        alt={`${CATEGORY_LABELS[category]} — ${ref.label ?? "referencia"}`}
                        title={ref.label ?? ""}
                      />
                    ))}
                  </div>
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    disabled={uploading}
                    onChange={(e) =>
                      uploadReference(profile.id, category, e.target.files?.[0])
                    }
                  />
                </div>
              );
            })}
            <button
              className="secondary"
              onClick={() => {
                api
                  .deleteProfile(profile.id)
                  .then(refresh)
                  .catch((err: Error) => setError(err.message));
              }}
            >
              Eliminar perfil
            </button>
          </section>
        ))}
      </div>
      {profiles.length === 0 && (
        <p className="muted">Aún no hay perfiles. Crea el primero arriba.</p>
      )}
    </>
  );
}
