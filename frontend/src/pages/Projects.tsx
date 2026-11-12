import { useEffect, useState } from "react";
import { api } from "../api";
import type { Project } from "../types";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = () => {
    api
      .listProjects()
      .then(setProjects)
      .catch((err: Error) => setError(err.message));
  };

  useEffect(refresh, []);

  const createProject = async () => {
    if (!name.trim()) return;
    setError(null);
    try {
      await api.createProject(name.trim(), description.trim() || undefined);
      setName("");
      setDescription("");
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <>
      <h2>Proyectos</h2>
      <p className="muted">
        Un proyecto agrupa los trabajos de edición de una sesión o una serie de fotos.
      </p>

      <section className="card">
        <h3>Nuevo proyecto</h3>
        <label htmlFor="project-name">Nombre</label>
        <input
          id="project-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Ej. Sesión estudio — noviembre"
        />
        <label htmlFor="project-description">Descripción</label>
        <input
          id="project-description"
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Opcional"
        />
        <button className="primary" onClick={createProject}>
          Crear proyecto
        </button>
      </section>

      {error && <div className="error">{error}</div>}

      <div className="grid">
        {projects.map((project) => (
          <section className="card" key={project.id}>
            <h3>{project.name}</h3>
            {project.description && <p className="muted">{project.description}</p>}
            <p className="muted">
              Creado: {new Date(project.created_at).toLocaleString("es-MX")}
            </p>
            <button
              className="secondary"
              onClick={() => {
                api
                  .deleteProject(project.id)
                  .then(refresh)
                  .catch((err: Error) => setError(err.message));
              }}
            >
              Eliminar proyecto
            </button>
          </section>
        ))}
      </div>
      {projects.length === 0 && (
        <p className="muted">Aún no hay proyectos. Crea el primero arriba.</p>
      )}
    </>
  );
}
