import { getRole, logout } from "../api";
import { useNavigate } from "react-router-dom";

type Props = {
  theme: string;
  setTheme: (t: string) => void;
  fontSize: string;
  setFontSize: (f: string) => void;
};

const SIZES = ["90", "100", "115"];
const SIZE_LABELS: Record<string, string> = {
  "90": "Decrease text size",
  "100": "Default text size",
  "115": "Increase text size",
};

export default function UtilityBar({ theme, setTheme, fontSize, setFontSize }: Props) {
  const nav = useNavigate();
  const role = getRole();
  return (
    <>
      <span className="role-badge">{role || "guest"}</span>
      {SIZES.map((s) => (
        <button
          key={s}
          onClick={() => setFontSize(s)}
          aria-label={SIZE_LABELS[s]}
          aria-pressed={s === fontSize}
        >
          {s === "90" ? "A−" : s === "100" ? "A" : "A+"}
        </button>
      ))}
      <button
        onClick={() => setTheme(theme === "light" ? "dark" : "light")}
        aria-label={theme === "light" ? "Switch to dark theme" : "Switch to light theme"}
      >
        {theme === "light" ? "☾" : "☀"}
      </button>
      <button
        onClick={() => {
          logout();
          nav("/login");
        }}
      >
        Logout
      </button>
    </>
  );
}
