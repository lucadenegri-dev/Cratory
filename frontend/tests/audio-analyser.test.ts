import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/* Il grafo dell'analizzatore non deve mai azzittire il player — nemmeno col
 * tempo.
 *
 * Una volta innestato, l'elemento suona SOLO attraverso il contesto Web Audio
 * (createMediaElementSource è irreversibile). WebKit, il motore del webview
 * del bundle desktop, quel contesto lo toglie da `running` per conto suo:
 * allo stop del Mac interrompe ogni sessione media (`suspendPlayback`), e al
 * risveglio lo riprende solo se in quel momento stava suonando — un player
 * lasciato in pausa resta con il contesto `suspended`. Da lì il play
 * successivo risultava in riproduzione ma muto, fino al riavvio. */

class FakeContext {
  static instances: FakeContext[] = [];
  state: AudioContextState = "running";
  sampleRate = 48000;
  destination = {};
  resume = vi.fn(() => {
    this.state = "running";
    return Promise.resolve();
  });
  createMediaElementSource = vi.fn(() => ({ connect: vi.fn() }));
  constructor() {
    FakeContext.instances.push(this);
  }
  createAnalyser() {
    return { fftSize: 0, smoothingTimeConstant: 0, frequencyBinCount: 512, connect: vi.fn() };
  }
}

async function freshModule() {
  vi.resetModules();
  return import("@/lib/audio-analyser");
}

function ownedAudio(): HTMLAudioElement {
  const el = document.createElement("audio");
  el.src = "/api/tracks/5/audio";
  return el;
}

beforeEach(() => {
  FakeContext.instances = [];
  vi.stubGlobal("AudioContext", FakeContext);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("attachAnalyser", () => {
  it("innesta la traccia posseduta a contesto in esecuzione", async () => {
    const { attachAnalyser, primeOnFirstGesture } = await freshModule();
    primeOnFirstGesture();
    window.dispatchEvent(new Event("pointerdown"));
    const el = ownedAudio();

    attachAnalyser(el);

    const [ctx] = FakeContext.instances;
    expect(ctx.createMediaElementSource).toHaveBeenCalledWith(el);
  });

  it("al play di un elemento già innestato riprende il contesto che WebKit ha sospeso", async () => {
    const { attachAnalyser, primeOnFirstGesture } = await freshModule();
    primeOnFirstGesture();
    window.dispatchEvent(new Event("pointerdown"));
    const el = ownedAudio();
    attachAnalyser(el);
    const [ctx] = FakeContext.instances;
    ctx.resume.mockClear();

    // Il Mac va in stop col player in pausa: al risveglio il contesto resta sospeso.
    ctx.state = "suspended";
    attachAnalyser(el); // il play successivo, sullo stesso elemento

    expect(ctx.resume).toHaveBeenCalledTimes(1);
    expect(ctx.state).toBe("running");
    // Riprendere non vuol dire innestare di nuovo: l'innesto resta uno solo.
    expect(ctx.createMediaElementSource).toHaveBeenCalledTimes(1);
  });

  it("vale anche per lo stato `interrupted` di WebKit", async () => {
    const { attachAnalyser, primeOnFirstGesture } = await freshModule();
    primeOnFirstGesture();
    window.dispatchEvent(new Event("pointerdown"));
    const el = ownedAudio();
    attachAnalyser(el);
    const [ctx] = FakeContext.instances;
    ctx.resume.mockClear();

    ctx.state = "interrupted" as AudioContextState;
    attachAnalyser(el);

    expect(ctx.resume).toHaveBeenCalledTimes(1);
  });
});
