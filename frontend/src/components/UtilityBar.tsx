import { getRole, logout } from "../api";
import { useNavigate } from "react-router-dom";

type Props = {
  theme: string;
  setTheme: (t: string) => void;
  fontSize: string;
  setFontSize: (f: string) => void;
};

const SIZES = ["90", "100", "115"];

export default function UtilityBar({ theme, setTheme, fontSize, setFontSize }: Props) {
  const nav = useNavigate();
  const role = getRole();
  return (
    <div className="utility-bar">
      <span className="role-badge">{role || "guest"}</span>
      <span>Text size:</span>
      {SIZES.map((s) => (
        <button
          key={s}
          onClick={() => setFontSize(s)}
          style={s === fontSize ? { borderColor: "#fac605", color: "#fff" } : undefined}
        >
          {s === "90" ? "A−" : s === "100" ? "A" : "A+"}
        </button>
      ))}
      <button onClick={() => setFontSize("100")}>⟳</button>
      <button onClick={() => setTheme(theme === "light" ? "dark" : "light")}>
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
