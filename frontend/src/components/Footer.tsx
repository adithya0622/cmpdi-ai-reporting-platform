import { NavLink } from "react-router-dom";

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <div>
          <h4>CMPDI AI Reporting Platform</h4>
          <p className="src" style={{ color: "#b8b3d9" }}>
            AI-assisted geological, mining and production intelligence for CMPDI/CIL subsidiaries.
          </p>
        </div>
        <nav aria-label="Footer navigation">
          <h4>Quick Links</h4>
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            <li><NavLink to="/documents">Documents</NavLink></li>
            <li><NavLink to="/reports">Reports</NavLink></li>
            <li><NavLink to="/analytics">Analytics</NavLink></li>
            <li><NavLink to="/query">Ask the Corpus</NavLink></li>
          </ul>
        </nav>
        <div>
          <h4>Platform</h4>
          <span>Version 0.3.0</span>
          <span>Operates fully on-premise / air-gapped</span>
          <span>Data never leaves the CMPDI network</span>
        </div>
      </div>
      <div className="footer-bottom">
        Central Mine Planning & Design Institute — Government of India Enterprise
      </div>
    </footer>
  );
}
