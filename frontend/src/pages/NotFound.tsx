import { useNavigate } from "react-router-dom";
import { Button } from "../components/ui/Button";

export function NotFound() {
  const navigate = useNavigate();
  return (
    <div className="min-h-[60vh] grid place-items-center">
      <div className="max-w-md w-full rounded-[var(--radius)] border border-mist/70 bg-paper/70 shadow-paper p-6">
        <div className="font-heading text-lg">404</div>
        <div className="mt-2 text-sm text-stone">这个页面不存在。</div>
        <div className="mt-4 flex gap-2">
          <Button tone="orange" onClick={() => navigate("/")}>回到 Chat</Button>
          <Button variant="subtle" onClick={() => navigate("/signals")}>去 Signals</Button>
        </div>
      </div>
    </div>
  );
}

