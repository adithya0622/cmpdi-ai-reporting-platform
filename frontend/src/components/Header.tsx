import { useState } from "react";
import { NavLink } from "react-router-dom";
import { getRole } from "../api";

type NavItem = {
  label: string;
  to?: string;
  children?: { to: string; label: string }[];
};

const NAV: NavItem[] = [
  { label: "Home", to: "/" },
  {
    label: "Documents",
    children: [
      { to: "/documents", label: "Upload & Browse" },
      { to: "/review", label: "Review Queue" },
    ],
  },
  {
    label: "Reports",
    children: [
      { to: "/reports", label: "Generate Report" },
      { to: "/reports", label: "Report Archive" },
    ],
  },
  {
    label: "Analytics",
    children: [
      { to: "/analytics", label: "Word Cloud & Topics" },
      { to: "/analytics", label: "Production Trends" },
      { to: "/analytics", label: "Topic Trends" },
    ],
  },
  { label: "Query", to: "/query" },
];

export default function Header() {
  const [open, setOpen] = useState(false);
  const role = getRole();
  const items: NavItem[] =
    role === "admin"
      ? [...NAV, { label: "Admin", children: [{ to: "/admin", label: "Users & Jobs" }, { to: "/admin", label: "Audit Log" }, { to: "/admin", label: "System Health" }] }]
      : NAV;

  return (
    <header className="site-header">
      <div className="header-inner">
        <NavLink to="/" className="logo-block">
          <div className="logo-mark">CMPDIL</div>
          <div className="logo-text">
            <b>CMPDI AI Reporting Platform</b>
            <span>AI-assisted geological & mining intelligence</span>
          </div>
        </NavLink>
        <button className="nav-toggle" onClick={() => setOpen(!open)} aria-label="Toggle navigation">
          ☰
        </button>
        <nav className={"nav" + (open ? " open" : "")}>
          <ul>
            {items.map((item) =>
              item.to ? (
                <li key={item.label}>
                  <NavLink to={item.to} end={item.to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>
                    {item.label}
                  </NavLink>
                </li>
              ) : (
                <li key={item.label}>
                  <span className="nav-link" tabIndex={0}>{item.label}</span>
                  <ul className="dropdown-menu">
                    {(item.children || []).map((c, i) => (
                      <li key={i}>
                        <NavLink to={c.to}>{c.label}</NavLink>
                      </li>
                    ))}
                  </ul>
                </li>
              )
            )}
          </ul>
        </nav>
      </div>
    </header>
  );
}
