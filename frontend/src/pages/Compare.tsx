import { useEffect, useState } from "react";
import { api, assetFileUrl } from "../api";
import type { Job } from "../types";
import { OPERATION_LABELS } from "../types";

export default function ComparePage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedId, setSelectedId] = useState<number | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listJobs()
      .then((items) => {
        const done = items.filter((job) => job.status === "completed");
        setJobs(done);
        if (done.length > 0) setSelectedId(done[0].id);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  const selected = jobs.find((job) => job.id === selectedId);

  return (
    <>
      <h2>Comparar original y procesada</h2>
      <p className="muted">
        El original siempre se conserva. Aquí ves la foto original junto a la versión
        procesada por el trabajo.
      </p>

      {error && <div className="error">{error}</div>}

      <section className="card">
        <label htmlFor="compare-job">Trabajo completado</label>
        <select
          id="compare-job"
          value={selectedId ?? ""}
          onChange={(e) => setSelectedId(Number(e.target.value))}
        >
          {jobs.map((job) => (
            <option key={job.id} value={job.id}>
              #{job.id} — {OPERATION_LABELS[job.operation] ?? job.operation} (
              {new Date(job.created_at).toLocaleDateString("es-MX")})
            </option>
          ))}
        </select>
      </section>

      {selected && (
        <section className="card">
          <div className="compare">
            <figure>
              <img src={assetFileUrl(selected.input_asset_id)} alt="Foto original" />
              <figcaption>Original (asset #{selected.input_asset_id})</figcaption>
            </figure>
            <figure>
              {selected.output_asset_id ? (
                <img
                  src={assetFileUrl(selected.output_asset_id)}
                  alt="Foto procesada"
                />
              ) : (
                <p className="muted">Sin resultado.</p>
              )}
              <figcaption>Procesada (asset #{selected.output_asset_id})</figcaption>
            </figure>
          </div>
          <p className="muted">“{selected.intent_text}”</p>
        </section>
      )}
      {jobs.length === 0 && (
        <p className="muted">Aún no hay trabajos completados para comparar.</p>
      )}
    </>
  );
}
