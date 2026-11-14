import { useEffect, useState } from "react";

// Minimal hash router: #/work, #/lease/<id>, #/progress/<id>, #/thread/<id>/<decl>, #/admin.

export function navigate(path: string): void {
  window.location.hash = path;
}

export function useRoute(): string[] {
  const read = () => window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const onChange = () => setRoute(read());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
