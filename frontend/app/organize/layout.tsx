import { I18nProvider as OrganizeI18nProvider } from "@/lib/organize/i18n";

/* F1: Organize porta ancora il proprio dizionario e il proprio provider,
   annidato dentro quello di Cratory nel root layout. F5 fonde i due dizionari
   sotto la chiave `organize.*` e questo layout sparisce. */
export default function OrganizeLayout({ children }: { children: React.ReactNode }) {
  return <OrganizeI18nProvider>{children}</OrganizeI18nProvider>;
}
