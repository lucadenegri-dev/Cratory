"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { getSetupState } from "@/lib/api";

/* Al primo avvio porta al wizard. Reindirizza SOLO su risposta riuscita: col
   backend giù l'utente finirebbe in una procedura che non può funzionare, e
   quel caso ha già il suo messaggio in dashboard. */
export function SetupGate() {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    let annullato = false;
    getSetupState()
      .then(({ completed }) => {
        if (!annullato && !completed && pathname !== "/setup") router.replace("/setup");
      })
      .catch(() => { /* backend giù: si resta dove si è */ });
    return () => { annullato = true; };
  }, [pathname, router]);

  return null;
}
