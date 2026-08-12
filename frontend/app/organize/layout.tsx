import { I18nProvider as OrganizeI18nProvider } from "@/lib/organize/i18n";
import { JobsProvider as OrganizeJobsProvider } from "@/components/organize/jobs-provider";

/* F1: Organize porta ancora il proprio dizionario e il proprio provider,
   annidato dentro quello di Cratory nel root layout. F5 fonde i due dizionari
   sotto la chiave `organize.*` e questo layout sparisce.
   JobsProvider di Organize è annidato qui (non dentro editorial-shell.tsx di
   Organize, che non è montato: le pagine vivono nell'EditorialShell di
   Cratory). Il componente è autosufficiente: renderizza da sé la barra di
   progresso fissa in fondo pagina (GlobalProgress), quindi non richiede lo
   shell di Organize per funzionare. */
export default function OrganizeLayout({ children }: { children: React.ReactNode }) {
  return (
    <OrganizeI18nProvider>
      <OrganizeJobsProvider>{children}</OrganizeJobsProvider>
    </OrganizeI18nProvider>
  );
}
