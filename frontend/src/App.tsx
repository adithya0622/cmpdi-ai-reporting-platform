import { useEffect, useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { getRole, isLoggedIn } from "./api";
import Admin from "./pages/Admin";
import Analytics from "./pages/Analytics";
import Footer from "./components/Footer";
import Home from "./pages/Home";
import Query from "./pages/Query";
import Reports from "./pages/Reports";
import Review from "./pages/Review";
import Documents from "./pages/Documents";
import Login from "./pages/Login";
import HelpButton from "./components/HelpButton";
import UtilityBar from "./components/UtilityBar";

const PAGE_TITLES: Record<string, string> = {
  "/": "Home",
  "/documents": "Documents",
  "/review": "Review",
  "/reports": "Reports",
  "/analytics": "Analytics",
  "/query": "Query",
  "/admin": "Admin",
  "/login": "Login",
};

type NavItem = { to: string; label: string; icon: string; badge?: string };

function RouteAnnouncer() {
  const location = useLocation();
  const [announcement, setAnnouncement] = useState("");
  useEffect(() => {
    setAnnouncement(`Navigated to ${PAGE_TITLES[location.pathname] || "page"}`);
  }, [location.pathname]);
  return (
    <div aria-live="assertive" aria-atomic="true" className="sr-only">
      {announcement}
    </div>
  );
}

export default function App() {
  const [authed, setAuthed] = useState(isLoggedIn());
  const [theme, setTheme] = useState(localStorage.getItem("cmpdi_theme") || "light");
  const [fontSize, setFontSize] = useState(localStorage.getItem("cmpdi_fontsize") || "100");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    const t = setInterval(() => setAuthed(isLoggedIn()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("cmpdi_theme", theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.style.fontSize = fontSize + "%";
    localStorage.setItem("cmpdi_fontsize", fontSize);
  }, [fontSize]);

  const role = getRole();

  function Layout({ children }: { children: React.ReactNode }) {
    const NAV: NavItem[] = [
      { to: "/", label: "Home", icon: "⌂" },
      { to: "/documents", label: "Documents", icon: "🗂" },
      { to: "/reports", label: "Reports", icon: "🗎" },
      { to: "/analytics", label: "Analytics", icon: "📊" },
      { to: "/query", label: "Query", icon: "💬" },
      { to: "/review", label: "Review", icon: "✎" },
      ...(role === "admin" ? [{ to: "/admin", label: "Admin", icon: "⚙" }] : []),
    ];
    return (
      <>
        <a className="skip-link" href="#main">Skip to main content</a>
        <header className="gov-header">
          <div className="gov-topstrip">
            <div className="topstrip-inner">
              <div className="topstrip-links">
                <a href="https://www.india.gov.in" target="_blank" rel="noreferrer">india.gov.in</a>
                <a href="https://coal.gov.in" target="_blank" rel="noreferrer">Ministry of Coal</a>
                <a href="https://www.coalindia.in" target="_blank" rel="noreferrer">Coal India Limited</a>
                <a href="https://www.cmpdi.co.in" target="_blank" rel="noreferrer">CMPDI</a>
                <a href="https://koylashakti.coal.gov.in" target="_blank" rel="noreferrer">Koyla Shakti</a>
              </div>
              <div className="utility-slot" role="toolbar" aria-label="Accessibility and account tools">
                <UtilityBar
                  theme={theme}
                  setTheme={setTheme}
                  fontSize={fontSize}
                  setFontSize={setFontSize}
                />
              </div>
            </div>
          </div>
          <div className="gov-masthead">
            <div className="masthead-inner">
              <div className="masthead-emblem" aria-hidden="true">
                <div className="emblem-circle">स</div>
              </div>
              <div className="masthead-title">
                <b>CMPDI AI Reporting Platform</b>
                <span>Central Mine Planning &amp; Design Institute · A Government of India Enterprise · Ministry of Coal</span>
              </div>
              <div className="masthead-ugc">
                <span className="ugc-line1">सत्यमेव जयते</span>
                <span className="ugc-line2">भारत सरकार</span>
              </div>
            </div>
          </div>
        </header>
        <div className="gov-body">
          <button
            className="sidebar-toggle"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-expanded={sidebarOpen}
            aria-controls="side-nav"
          >
            ☰ Menu
          </button>
          <aside className={"gov-sidebar" + (sidebarOpen ? " open" : "")} aria-label="Primary">
            <nav>
              <p className="sidebar-heading">Menu</p>
              <ul id="side-nav">
                {NAV.map((item) => (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      end={item.to === "/"}
                      className={({ isActive }) => (isActive ? "active" : "")}
                      onClick={() => setSidebarOpen(false)}
                    >
                      <span className="nav-icon" aria-hidden="true">{item.icon}</span>
                      {item.label}
                    </NavLink>
                  </li>
                ))}
              </ul>
              <p className="sidebar-heading">External</p>
              <ul className="sidebar-external">
                <li><a href="https://coal.gov.in" target="_blank" rel="noreferrer">Ministry of Coal ↗</a></li>
                <li><a href="https://www.coalindia.in" target="_blank" rel="noreferrer">Coal India ↗</a></li>
                <li><a href="https://koylashakti.coal.gov.in" target="_blank" rel="noreferrer">Koyla Shakti ↗</a></li>
              </ul>
            </nav>
          </aside>
          <main id="main" className="gov-main">{children}</main>
        </div>
        <Footer />
        <HelpButton />
      </>
    );
  }

  const guard = (el: React.ReactNode) => (authed ? <Layout>{el}</Layout> : <Navigate to="/login" replace />);

  return (
    <>
      <RouteAnnouncer />
      <Routes>
        <Route path="/login" element={<Login onLogin={() => setAuthed(true)} />} />
        <Route path="/" element={guard(<Home />)} />
        <Route path="/dashboard" element={<Navigate to="/" replace />} />
        <Route path="/documents" element={guard(<Documents />)} />
        <Route path="/review" element={guard(<Review />)} />
        <Route path="/reports" element={guard(<Reports />)} />
        <Route path="/analytics" element={guard(<Analytics />)} />
        <Route path="/query" element={guard(<Query />)} />
        <Route path="/admin" element={guard(<Admin />)} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}
