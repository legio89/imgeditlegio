import { useEffect, useState } from "react";
import { api } from "../api";
import type { Job } from "../types";
import { OPERATION_LABELS } from "../types";

export default function HistoryPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  const refresh = () => {
    api
      .listJobs()
      .then(setJobs)
      .catch((err: Error) => setError(err.message));
  };

  useEffect(refresh, []);

  return (
    <>
      <h2>Historial de trabajos</h2>
      <p className="muted">
        Cada trabajo guarda su intención, sus parámetros y sus eventos. Las generaciones
        completadas quedan registradas para reproducirlas.
      </p>

      {error && <div className="error">{error}</div>}

      <button className="secondary" onClick={refresh}>
        Actualizar
      </button>

      {jobs.map((job) => (
        <section className="card" key={job.id}>
          <h3>
            Trabajo #{job.id} —{" "}
            <span className={`badge ${job.status}`}>{job.status}</span>
          </h3>
          <p>
            {OPERATION_LABELS[job.operation] ?? job.operation} · Motor: {job.engine} ·{" "}
            {new Date(job.created_at).toLocaleString("es-MX")}
          </p>
          <p className="muted">“{job.intent_text}”</p>
          {job.error && <div className="error">{job.error}</div>}
          <button
            className="secondary"
            onClick={() => setExpanded(expanded === job.id ? null : job.id)}
          >
            {expanded === job.id ? "Ocultar detalle" : "Ver detalle"}
          </button>
          {expanded === job.id && (
            <>
              <details open>
                <summary>Parámetros</summary>
                <pre className="params">{JSON.stringify(job.parameters, null, 2)}</pre>
              </details>
              <details open>
                <summary>Eventos ({job.events.length})</summary>
                <ul className="events">
                  {job.events.map((event) => (
                    <li key={event.id}>
                      <time>
                        {new Date(event.created_at).toLocaleTimeString("es-MX")}
                      </time>
                      <strong>{event.event_type}:</strong> {event.message}
                    </li>
                  ))}
                </ul>
              </details>
              {job.output_asset_id && (
                <p className="muted">
                  Resultado: asset #{job.output_asset_id} · Original: asset #
                  {job.input_asset_id}
                </p>
              )}
            </>
          )}
        </section>
      ))}
      {jobs.length === 0 && <p className="muted">Aún no hay trabajos.</p>}
    </>
  );
}
