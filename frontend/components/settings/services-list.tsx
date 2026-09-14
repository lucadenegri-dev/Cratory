"use client";

import { useCallback, useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import {
  getConfigSettings, setSoundcloudUsername, soundcloudStatus, spotifyLoginUrl,
  errText, type ConfigSettings, type ServiceStatus, type SlskdStatus, type SoundCloudStatus,
} from "@/lib/api";
import { runFingerprint, type FingerprintResult } from "@/lib/organize/api";
import { Alert, BTN_SIZE, BTN_VARIANT, Button, Input, Loading, Spinner } from "@/components/ui";
import { cn } from "@/lib/cn";
import { useT, type Dictionary } from "@/lib/i18n";
import { ServiceCard } from "@/components/setup/service-card";
import { SlskdRow } from "@/components/slskd-row";
import { PathField } from "@/components/setup/path-field";
import { SERVICE_FIELDS, type ServiceKey } from "@/lib/setup-services";

/* La lista unificata dei servizi esterni: una riga per servizio, semantica di
   stato unica, azioni inline dove servono (OAuth Spotify, login slskd,
   username SoundCloud, fingerprint AcoustID). Sostituisce la vecchia coppia
   lista Servizi + ProviderList di Organize e le card SoulseekCard e
   SoundCloudCard (fusione F1-F6: un prodotto, una lista). */

function statusLabel(s: ServiceStatus, t: Dictionary): { text: string; strong: boolean } {
  if (s.connected === true) return { text: t.settings.statusConnected, strong: true };
  if (s.connected === false) return { text: t.settings.statusToConnect, strong: false };
  if (s.configured) return { text: t.settings.statusActive, strong: true };
  return { text: t.settings.statusNotConfigured, strong: false };
}

export function ServicesList({ services, onServicesChanged }: {
  services: ServiceStatus[];
  /* Ricarica lo stato dei servizi del genitore (badge di riga): senza,
     dopo un salvataggio da riga espansa il pannello passa a "configurato"
     ma il badge sopra resta indietro finché non si ricarica la pagina.
     Opzionale per non rompere i chiamanti/test esistenti che non lo passano. */
  onServicesChanged?: () => void;
}) {
  const t = useT();
  const [expanded, setExpanded] = useState<string | null>(null);
  const [config, setConfig] = useState<ConfigSettings | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [soulseek, setSoulseek] = useState<SlskdStatus | null>(null);
  const loadConfig = useCallback(() => {
    getConfigSettings().then((value) => { setConfig(value); setConfigError(null); }).catch((e) => setConfigError(errText(e)));
  }, []);
  useEffect(loadConfig, [loadConfig]);
  const handleSaved = useCallback(() => {
    loadConfig();
    onServicesChanged?.();
  }, [loadConfig, onServicesChanged]);
  const names: Record<string, string> = { slskd: "Soulseek", anthropic: "Anthropic", acoustid: "AcoustID" };
  const order = ["spotify", "soundcloud", "slskd", "discogs", "musicbrainz", "acoustid", "anthropic"];
  return (
    <div className="border-t border-border">
      {[...services].sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key)).map((s) => {
        const name = names[s.key] ?? s.name;
        const editable = !!SERVICE_FIELDS[s.key as ServiceKey] || s.key === "soundcloud";
        const open = expanded === s.key;
        // Il login Soulseek arriva dalla riga slskd (onStatusChange): vale solo
        // se slskd è configurato, altrimenti «Disconnesso» fingerebbe un
        // demone spento dove manca proprio l'URL.
        const loggedIn = !!soulseek && soulseek.is_connected && soulseek.is_logged_in;
        const st = s.key === "slskd" && soulseek?.configured
          ? { text: loggedIn ? t.settings.statusConnected : t.settings.soulseekDisconnected, strong: loggedIn }
          : statusLabel(s, t);
        return (
          <section key={s.key} aria-label={name} className="border-b border-border py-5">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="min-w-0 flex-1 basis-64">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-fg-strong">{name}</h2>
                <p className="mt-1 text-sm text-muted">{t.settings.servicesMeta[s.key]?.detail ?? s.detail}</p>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <span className={`text-xs ${st.strong ? "text-fg-strong" : "text-muted"}`}>{st.text}</span>
                {editable && <Button size="sm" variant="outline" aria-expanded={open} aria-controls={`service-${s.key}`}
                  aria-label={`${open ? t.settings.collapseKeys : s.configured ? t.settings.manageButton : t.settings.configureButton} ${name}`}
                  onClick={() => setExpanded(open ? null : s.key)}>
                  {open ? t.settings.collapseKeys : s.configured ? t.settings.manageButton : t.settings.configureButton}
                </Button>}
              </div>
            </div>
            {editable && <div id={`service-${s.key}`} hidden={!open} className="mt-5 space-y-5 border-t border-border pt-5">
              {/* <a> nudo, non next/link: l'href è l'endpoint OAuth del backend,
                  che Link prefetcherebbe (avvio login senza click) e al click
                  tenterebbe da router client. Stesse classi del Button. */}
              {s.key === "spotify" && s.configured && <a href={spotifyLoginUrl()}
                className={cn("inline-flex items-center justify-center gap-2 font-medium uppercase tracking-wider transition-colors", BTN_VARIANT.outline, BTN_SIZE.sm)}>
                <ExternalLink size={14} /> {s.connected ? t.settings.reconnectButton : t.settings.connectButton}
              </a>}
              {s.key === "slskd" && <SlskdRow onStatusChange={setSoulseek} />}
              {s.key === "soundcloud" && <SoundCloudExtra t={t} />}
              {SERVICE_FIELDS[s.key as ServiceKey] && <>
                {configError && <Alert tone="danger">{configError}<Button size="sm" variant="outline" onClick={loadConfig}>{t.settings.retryButton}</Button></Alert>}
                {!config && !configError && <Loading />}
                {config && <ServiceCard service={s.key as ServiceKey} secrets={config.secrets}
                  redirectUri={config.spotify_redirect_uri} docsUrl={s.docs} onSaved={handleSaved} collapsibleGuide>
                  {s.key === "anthropic" && <PathField fieldKey="ai_model" label={t.setup.aiModelLabel}
                    value={config.ai_model.value} detail={t.settings.modelHint} canPick={false} kind="text" onSaved={setConfig} />}
                </ServiceCard>}
              </>}
              {s.key === "acoustid" && s.configured && <AcoustidExtra t={t} />}
            </div>}
          </section>
        );
      })}
    </div>
  );
}

function SoundCloudExtra({ t }: { t: Dictionary }) {
  const [status, setStatus] = useState<SoundCloudStatus | null>(null);
  const [username, setUsername] = useState("");
  const [saving, setSaving] = useState(false);
  /* Senza questa conferma il salvataggio riuscito era invisibile: il campo
     contiene gia' quello che l'utente ha scritto e il badge della riga viene
     da yt-dlp, non dall'username — premere Salva sembrava non fare nulla.
     Stessa forma di config-card, che la conferma la dava gia'. */
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    soundcloudStatus()
      .then((s) => { setStatus(s); setUsername(s.username ?? ""); })
      .catch(() => setStatus(null));
  }, []);

  const save = async () => {
    setError(null); setSaving(true); setSaved(false);
    try {
      setStatus(await setSoundcloudUsername(username.trim()));
      setSaved(true); setTimeout(() => setSaved(false), 1500);
    }
    catch (e) { setError(String((e as { message?: string })?.message ?? e)); }
    finally { setSaving(false); }
  };

  return (
    <div className="mt-3 grid gap-2 border border-border bg-bg p-3">
      {status && !status.available && <Alert tone="warning">{t.settings.soundcloudYtdlpUnavailable}</Alert>}
      {error && <Alert tone="danger">⚠ {error}</Alert>}
      {/* Un form, non tre elementi affiancati: scritto un username, il gesto
          naturale e' premere Invio, e fuori da un form non salvava niente. */}
      <form className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => { e.preventDefault(); if (!saving && username.trim() !== "") void save(); }}>
        <label htmlFor="settings-soundcloud-username" className="shrink-0 text-xs text-muted">{t.settings.usernameLabel}</label>
        <Input id="settings-soundcloud-username" className="min-w-0 flex-1" value={username}
          onChange={(e) => { setUsername(e.target.value); setSaved(false); }}
          placeholder={t.settings.usernamePlaceholder} disabled={saving} />
        <Button type="submit" size="sm" disabled={saving || username.trim() === ""}>
          {saving ? <Spinner /> : saved ? t.settings.savedLabel : t.common.save}
        </Button>
      </form>
    </div>
  );
}

function AcoustidExtra({ t }: { t: Dictionary }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<FingerprintResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const identify = async () => {
    setError(null); setBusy(true);
    try { setResult(await runFingerprint()); }
    catch (e) { setError(String((e as { message?: string })?.message ?? e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 border border-border bg-bg p-3">
      <Button size="sm" variant="outline" onClick={identify} disabled={busy}>
        {busy ? <><Spinner /> {t.settings.identifyBusy}</> : t.settings.identifyNow}
      </Button>
      {result && (
        <span className="text-xs text-muted">
          {t.settings.fpResult(result.identified, result.below_threshold, result.not_found, result.errors, result.total)}
        </span>
      )}
      {error && <Alert tone="danger">⚠ {error}</Alert>}
    </div>
  );
}
