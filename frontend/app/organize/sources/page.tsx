"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

// La pagina Sources è stata fusa in Files: qui solo un redirect per vecchi link.
export default function SourcesRedirect() {
  const router = useRouter();
  useEffect(() => { router.replace("/organize/files"); }, [router]);
  return null;
}
