import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { isLoggedIn } from "./api";
import Admin from "./pages/Admin";
import Analytics from "./pages/Analytics";
import Footer from "./components/Footer";
import Header from "./components/Header";
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

  const guard = (el: React.ReactNode) => (authed ? <Layout>{el}</Layout> : <Navigate to="/login" replace />);

  function Layout({ children }: { children: React.ReactNode }) {
    return (
      <>
        <a className="skip-link" href="#main">Skip to main content</a>
        <UtilityBar theme={theme} setTheme={setTheme} fontSize={fontSize} setFontSize={setFontSize} />
        <Header />
        <main id="main">{children}</main>
        <Footer />
        <HelpButton />
      </>
    );
  }

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
