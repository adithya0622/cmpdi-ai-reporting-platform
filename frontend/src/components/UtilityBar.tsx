import { getRole, logout } from "../api";
import { useNavigate } from "react-router-dom";

type Props = {
  theme: string;
  setTheme: (t: string) => void;
  fontSize: string;
  setFontSize: (f: string) => void;
};

const SIZES = ["90", "100", "115"];
const SIZE_LABELS: Record<string, string> = { "90": "Decrease text size", "100": "Default text size", "115": "Increase text size" };

export default function UtilityBar({ theme, setTheme, fontSize, setFontSize }: Props) {
  const nav = useNavigate();
  const role = getRole();
  return (
    <div className="utility-bar" role="toolbar" aria-label="Accessibility tools">
      <span className="role-badge">{role || "guest"}</span>
      <span id="text-size-label">Text size:</span>
      {SIZES.map((s) => (
        <button
          key={s}
          onClick={() => setFontSize(s)}
          aria-label={SIZE_LABELS[s]}
          aria-pressed={s === fontSize}
          style={s === fontSize ? { borderColor: "#fac605", color: "#fff" } : undefined}
        >
          {s === "90" ? "A−" : s === "100" ? "A" : "A+"}
        </button>
      ))}
      <button onClick={() => setFontSize("100")} aria-label="Reset text size">⟳</button>
      <button onClick={() => setTheme(theme === "light" ? "dark" : "light")} aria-label={theme === "light" ? "Switch to dark theme" : "Switch to light theme"}>
        {theme === "light" ? "☀ Light" : "☾ Dark"}
      </button>
      <button
        onClick={() => {
          logout();
          nav("/login");
        }}
      >
        Logout
      </button>
    </div>
  );
}
