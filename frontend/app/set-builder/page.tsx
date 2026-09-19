"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { Loading } from "@/components/ui";

/** Il vecchio Set Builder: un form che generava un set intero, con una fase di
 *  curatela AI. Rimosso il 2026-09-19 — i set si preparano a mano, e il motore
 *  deterministico e' diventato uno strumento dentro il set («riempi il varco»).
 *
 *  La rotta resta come reindirizzamento perche' ci puntano ancora i link da
 *  playlist ed etichette, e perche' qualcuno potrebbe averla nei preferiti: un
 *  404 al posto di una pagina che c'era e' un modo scortese di dire che una
 *  cosa e' cambiata. La playlist di partenza viaggia nella query. */
export default function SetBuilderPage() {
  return <Suspense><Redirect /></Suspense>;
}

function Redirect() {
  const router = useRouter();
  const playlist = useSearchParams().get("playlist");
  useEffect(() => {
    router.replace(playlist ? `/sets?playlist=${playlist}` : "/sets");
  }, [router, playlist]);
  return <Loading />;
}
