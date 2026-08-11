import { redirect } from "next/navigation";

// La pagina Sources è stata fusa in Files: qui solo un redirect per vecchi link.
// Server Component + redirect() (come app/organize/page.tsx), non un
// useEffect lato client con router.replace: quel pattern qui non partiva mai
// in modo affidabile (bug riscontrato durante l'estensione della suite E2E ai
// path /organize/*, corretto qui — nessuna interattività client necessaria
// per una pagina che deve solo reindirizzare).
export default function SourcesRedirect() {
  redirect("/organize/files");
}
