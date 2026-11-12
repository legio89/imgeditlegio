import { useEffect, useState } from "react";
import { api } from "./api";
import ComparePage from "./pages/Compare";
import HistoryPage from "./pages/History";
import ProfilesPage from "./pages/Profiles";
import ProjectsPage from "./pages/Projects";
import StudioPage from "./pages/Studio";

type Tab = "profiles" | "projects" | "studio" | "history" | "compare";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "profiles", label: "Perfiles" },
  { id: "projects", label: "Proyectos" },
  { id: "studio", label: "Estudio" },
  { id: "history", label: "Historial" },
  { id: "compare", label: "Comparar" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("studio");
  const [engineStatus, setEngineStatus] = useState<string>("…");
  const [backendDown, setBackendDown] = useState(false);

  useEffect(() => {
    api
      .engine()
      .then((info) => {
        setBackendDown(false);
        setEngineStatus(
          info.status === "ok"
            ? `Motor: ${info.engine}`
            : `Motor: ${info.engine} (no disponible)`,
        );
      })
      .catch(() => {
        setBackendDown(true);
        setEngineStatus("Backend no disponible");
      });
  }, []);

  return (
    <>
      <header className="topbar">
        <div>
          <h1>VEXTAR</h1>
          <div className="subtitle">Estudio fotográfico con IA · local y privado</div>
        </div>
        <div className="subtitle">{engineStatus}</div>
        <nav className="tabs">
          {TABS.map((item) => (
            <button
              key={item.id}
              className={tab === item.id ? "active" : ""}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </header>
      <main>
        {backendDown && (
          <div className="error">
            No se pudo conectar con el backend. Inicia el backend en
            http://localhost:8000 (ver README) y recarga la página.
          </div>
        )}
        {tab === "profiles" && <ProfilesPage />}
        {tab === "projects" && <ProjectsPage />}
        {tab === "studio" && <StudioPage />}
        {tab === "history" && <HistoryPage />}
        {tab === "compare" && <ComparePage />}
      </main>
      <footer>
        VEXTAR 0.1.0 · Todo el procesamiento pasa por el backend; el frontend nunca
        habla directo con ComfyUI.
      </footer>
    </>
  );
}
