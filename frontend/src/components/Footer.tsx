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
        <div>
          <h4>Quick Links</h4>
          <NavLink to="/documents">Documents</NavLink>
          <NavLink to="/reports">Reports</NavLink>
          <NavLink to="/analytics">Analytics</NavLink>
          <NavLink to="/query">Ask the Corpus</NavLink>
        </div>
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
