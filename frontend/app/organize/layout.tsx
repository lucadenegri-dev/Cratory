import { JobsProvider as OrganizeJobsProvider } from "@/components/organize/jobs-provider";

/* Resta solo per annidare il JobsProvider di Organize, che renderizza da sé la
   propria barra di progresso fissa in fondo pagina. Il provider i18n non serve
   più: da F5 il dizionario è uno solo e il provider vive nel root layout.
   Questo file sparisce quando i due JobsProvider diventano uno. */
export default function OrganizeLayout({ children }: { children: React.ReactNode }) {
  return <OrganizeJobsProvider>{children}</OrganizeJobsProvider>;
}
