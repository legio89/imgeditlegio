import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { IntentAnalysis, Job, Profile, Project, Reference } from "../types";
import { CATEGORY_LABELS, OPERATION_LABELS } from "../types";

export default function StudioPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [projectId, setProjectId] = useState<number | undefined>(undefined);
  const [selectedProfiles, setSelectedProfiles] = useState<number[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [intentText, setIntentText] = useState("");
  const [analysis, setAnalysis] = useState<IntentAnalysis | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [poseReferenceAssetId, setPoseReferenceAssetId] = useState<number | undefined>(
    undefined,
  );
  const [outfitReferenceAssetId, setOutfitReferenceAssetId] = useState<
    number | undefined
  >(undefined);
  const [modelFamily, setModelFamily] = useState<"sd15" | "flux">("sd15");
  const pollRef = useRef<number | undefined>(undefined);

  // Referencias de los perfiles seleccionados, para los selectores de pose
  // y de atuendo: cada opción es un asset de un perfil.
  const selectedReferences: { profile: Profile; reference: Reference }[] = profiles
    .filter((profile) => selectedProfiles.includes(profile.id))
    .flatMap((profile) =>
      profile.references.map((reference) => ({ profile, reference })),
    );

  useEffect(() => {
    api.listProjects().then((items) => {
      setProjects(items);
      if (items.length > 0) setProjectId(items[0].id);
    });
    api.listProfiles().then(setProfiles);
    return () => window.clearInterval(pollRef.current);
  }, []);

  const toggleProfile = (id: number) => {
    setSelectedProfiles((current) =>
      current.includes(id) ? current.filter((x) => x !== id) : [...current, id],
    );
    // Al cambiar los perfiles, las referencias elegidas pueden dejar de
    // existir: se limpian para no enviar un asset de otro perfil.
    setPoseReferenceAssetId(undefined);
    setOutfitReferenceAssetId(undefined);
  };

  const analyze = async () => {
    if (!intentText.trim()) return;
    setError(null);
    try {
      const result = await api.parseIntent(intentText.trim());
      setAnalysis(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const submitJob = async () => {
    if (!projectId || !file || !intentText.trim()) {
      setError("Elige un proyecto, sube la foto original y describe la edición.");
      return;
    }
    setBusy(true);
    setError(null);
    setJob(null);
    try {
      const asset = await api.uploadAsset(file, "original", projectId);
      const parameters: Record<string, unknown> = {
        model_family: modelFamily,
      };
      if (poseReferenceAssetId !== undefined) {
        parameters.pose_reference_asset_id = poseReferenceAssetId;
      }
      if (outfitReferenceAssetId !== undefined) {
        parameters.outfit_reference_asset_id = outfitReferenceAssetId;
      }
      const created = await api.createJob({
        project_id: projectId,
        intent_text: intentText.trim(),
        input_asset_id: asset.id,
        profile_ids: selectedProfiles,
        operation: analysis?.operation,
        parameters,
      });
      setJob(created);
      pollRef.current = window.setInterval(async () => {
        const updated = await api.getJob(created.id);
        setJob(updated);
        if (["completed", "failed", "cancelled"].includes(updated.status)) {
          window.clearInterval(pollRef.current);
          setBusy(false);
        }
      }, 1000);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  };

  return (
    <>
      <h2>Estudio</h2>
      <p className="muted">
        Describe lo que quieres conseguir y VEXTAR interpreta la intención, elige la
        operación y ejecuta el trabajo. El original nunca se sobrescribe: el resultado
        se guarda aparte.
      </p>

      {error && <div className="error">{error}</div>}

      <section className="card">
        <label htmlFor="studio-project">Proyecto</label>
        <select
          id="studio-project"
          value={projectId ?? ""}
          onChange={(e) => setProjectId(Number(e.target.value))}
        >
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </select>
        {projects.length === 0 && (
          <p className="muted">Primero crea un proyecto en la pestaña Proyectos.</p>
        )}

        <label>Modelos (perfiles) involucrados</label>
        {profiles.length === 0 && (
          <p className="muted">
            Sin perfiles todavía. Puedes trabajar sin perfil, o crear uno en la pestaña
            Perfiles.
          </p>
        )}
        {profiles.map((profile) => (
          <label key={profile.id} style={{ display: "flex", gap: "0.5rem" }}>
            <input
              type="checkbox"
              checked={selectedProfiles.includes(profile.id)}
              onChange={() => toggleProfile(profile.id)}
            />
            {profile.name}
          </label>
        ))}

        {selectedProfiles.length > 0 && (
          <>
            <label htmlFor="studio-pose-reference">Referencia de pose</label>
            <select
              id="studio-pose-reference"
              value={poseReferenceAssetId ?? ""}
              onChange={(e) =>
                setPoseReferenceAssetId(
                  e.target.value ? Number(e.target.value) : undefined,
                )
              }
            >
              <option value="">Sin referencia (usa la pose de la foto)</option>
              {selectedReferences.map(({ profile, reference }) => (
                <option key={reference.asset_id} value={reference.asset_id}>
                  {profile.name} — {CATEGORY_LABELS[reference.category]} —{" "}
                  {reference.asset.filename}
                  {reference.label ? ` (${reference.label})` : ""}
                </option>
              ))}
            </select>
            <p className="muted">
              Para cambios de pose: la imagen de referencia marca la postura nueva
              (ControlNet OpenPose).
            </p>

            <label htmlFor="studio-outfit-reference">Referencia de atuendo</label>
            <select
              id="studio-outfit-reference"
              value={outfitReferenceAssetId ?? ""}
              onChange={(e) =>
                setOutfitReferenceAssetId(
                  e.target.value ? Number(e.target.value) : undefined,
                )
              }
            >
              <option value="">Sin referencia (el cambio se guía por texto)</option>
              {selectedReferences.map(({ profile, reference }) => (
                <option key={reference.asset_id} value={reference.asset_id}>
                  {profile.name} — {CATEGORY_LABELS[reference.category]} —{" "}
                  {reference.asset.filename}
                  {reference.label ? ` (${reference.label})` : ""}
                </option>
              ))}
            </select>
            <p className="muted">
              Para cambios de vestimenta: la imagen de referencia muestra el atuendo
              nuevo. Quitar una prenda no necesita referencia.
            </p>
          </>
        )}

        <label htmlFor="studio-family">Familia de modelos</label>
        <select
          id="studio-family"
          value={modelFamily}
          onChange={(e) => setModelFamily(e.target.value as "sd15" | "flux")}
        >
          <option value="sd15">Stable Diffusion 1.5 (con IP-Adapter)</option>
          <option value="flux">FLUX.1 (mayor calidad, sin IP-Adapter)</option>
        </select>
        <p className="muted">
          FLUX necesita sus modelos instalados en ComfyUI (ver la guía de instalación).
          Con FLUX la identidad se condiciona por texto y por la imagen base.
        </p>

        <label htmlFor="studio-file">Foto original</label>
        <input
          id="studio-file"
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />

        <label htmlFor="studio-intent">¿Qué quieres conseguir?</label>
        <textarea
          id="studio-intent"
          value={intentText}
          onChange={(e) => setIntentText(e.target.value)}
          placeholder="Ej. Mejorar la nitidez y la resolución de la foto, conservando su aspecto fotográfico"
        />
        <div>
          <button className="secondary" onClick={analyze} disabled={!intentText.trim()}>
            Analizar intención
          </button>
        </div>

        {analysis && (
          <div className="notice">
            <strong>Operación detectada:</strong>{" "}
            {OPERATION_LABELS[analysis.operation] ?? analysis.operation} (
            {Math.round(analysis.confidence * 100)}% de confianza)
            <br />
            {analysis.summary}
            {analysis.clarification_questions.length > 0 && (
              <>
                <br />
                <strong>Preguntas para afinar:</strong>
                <ul>
                  {analysis.clarification_questions.map((question) => (
                    <li key={question}>{question}</li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}

        <button className="primary" onClick={submitJob} disabled={busy}>
          {busy ? "Trabajando…" : "Crear trabajo"}
        </button>
      </section>

      {job && (
        <section className="card">
          <h3>
            Trabajo #{job.id} —{" "}
            <span className={`badge ${job.status}`}>{job.status}</span>
          </h3>
          <p className="muted">
            Operación: {OPERATION_LABELS[job.operation] ?? job.operation} · Motor:{" "}
            {job.engine}
            {typeof job.parameters?.evaluation === "object" &&
              job.parameters.evaluation !== null && (
                <>
                  {" · Coherencia: "}
                  {Math.round(
                    ((job.parameters.evaluation as { score?: number }).score ?? 0) *
                      100,
                  )}
                  %
                </>
              )}
          </p>
          {job.error && <div className="error">{job.error}</div>}
          <ul className="events">
            {job.events.map((event) => (
              <li key={event.id}>
                <time>{new Date(event.created_at).toLocaleTimeString("es-MX")}</time>
                {event.message}
              </li>
            ))}
          </ul>
          {job.status === "completed" && job.output_asset_id && (
            <p>
              Resultado listo. Compáralo en la pestaña <strong>Comparar</strong> o
              revísalo en el <strong>Historial</strong>.
            </p>
          )}
        </section>
      )}
    </>
  );
}
