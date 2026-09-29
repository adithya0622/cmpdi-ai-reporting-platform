import { NavLink } from "react-router-dom";

const TOP_ROW = [
  { label: "Home", href: "https://www.india.gov.in", title: "National Portal of India" },
  { label: "Ministry of Coal", href: "https://coal.gov.in", title: "Ministry of Coal, Government of India" },
  { label: "Coal India Limited", href: "https://www.coalindia.in", title: "Coal India Limited" },
  { label: "CMPDI", href: "https://www.cmpdi.co.in", title: "Central Mine Planning & Design Institute" },
  { label: "Koyla Shakti", href: "https://koylashakti.coal.gov.in", title: "Smart Coal Analytics Dashboard, Ministry of Coal" },
  { label: "Coal Controller", href: "https://coalcontroller.gov.in", title: "Coal Controller's Organisation" },
];

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="footer-top">
        <div className="footer-col">
          <h4>About the Platform</h4>
          <p className="src" style={{ color: "#b8b3d9" }}>
            AI-assisted document processing, extraction and reporting for geological, mining and
            production intelligence. Operates fully on-premise; data never leaves the CMPDI network.
          </p>
        </div>
        <div className="footer-col">
          <h4>Platform Links</h4>
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            <li><NavLink to="/documents">Documents</NavLink></li>
            <li><NavLink to="/reports">Reports</NavLink></li>
            <li><NavLink to="/analytics">Analytics</NavLink></li>
            <li><NavLink to="/query">Ask the AI</NavLink></li>
            <li><NavLink to="/review">Review Queue</NavLink></li>
          </ul>
        </div>
        <div className="footer-col">
          <h4>Help</h4>
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            <li><NavLink to="/query">Query Guide</NavLink></li>
            <li><span title="Help is available on every page">In-app Help Assistant</span></li>
            <li><a href="https://www.india.gov.in" target="_blank" rel="noreferrer">india.gov.in</a></li>
          </ul>
        </div>
        <div className="footer-col">
          <h4>Version</h4>
          <p className="src" style={{ color: "#b8b3d9", margin: 0 }}>
            v0.3.0 · SIH 2026
            <br />
            Sovereign on-premise deployment
          </p>
        </div>
      </div>
      <div className="footer-links-row">
        {TOP_ROW.map((l) => (
          <a key={l.label} href={l.href} target="_blank" rel="noreferrer" title={l.title}>
            {l.label}
          </a>
        ))}
      </div>
      <div className="footer-bottom">
        <span>
          Website content is owned &amp; maintained by the Central Mine Planning &amp; Design Institute.
        </span>
        <span>
          <a href="https://www.india.gov.in" target="_blank" rel="noreferrer">india.gov.in</a>
          {" · "}
          <a href="https://coal.gov.in" target="_blank" rel="noreferrer">Ministry of Coal</a>
        </span>
        <span>
          Last Updated: {new Date().toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}
          {" · "}
          {new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
        </span>
      </div>
    </footer>
  );
}
