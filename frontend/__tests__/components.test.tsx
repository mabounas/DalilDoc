import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import IdleScreen from "@/components/IdleScreen";
import ResponseDisplay, { spokenText } from "@/components/ResponseDisplay";
import TextInput from "@/components/TextInput";
import VoiceInput from "@/components/VoiceInput";
import * as api from "@/lib/api";
import { answerOffline, type OfflinePack } from "@/lib/offline";
import { pickVoice, SilenceDetector, toSpeech } from "@/lib/speech";

jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  synthesize: jest.fn(),
  transcribe: jest.fn(),
  getVoiceCapabilities: jest.fn(),
}));
const mockedSynthesize = api.synthesize as jest.MockedFunction<typeof api.synthesize>;
const mockedTranscribe = api.transcribe as jest.MockedFunction<typeof api.transcribe>;
const mockedCaps = api.getVoiceCapabilities as jest.MockedFunction<typeof api.getVoiceCapabilities>;

const push = jest.fn();
jest.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
jest.mock("react-simple-keyboard", () => ({
  __esModule: true,
  default: ({ rtl }: { rtl: boolean }) => <div data-testid="virtual-keyboard" data-rtl={String(rtl)} />,
}));
jest.mock("qrcode.react", () => ({ QRCodeSVG: () => <svg data-testid="qr" /> }));

const RESULT: api.QueryResult = {
  reponse: "CNIE — première demande\nDocuments requis :",
  langue: "fr",
  demarche_id: "cin-premiere-demande",
  documents: [
    { ordre: 1, nom: "Certificat de résidence", obligatoire: true, condition: null, format: [] },
    { ordre: 2, nom: "Quatre photographies d'identité", obligatoire: true, condition: null, format: [] },
  ],
  score_confiance: 0.8,
  hors_perimetre: false,
  sources: ["https://www.cnie.ma/static/procedure"],
  temps_ms: 12,
};

beforeEach(() => {
  mockedSynthesize.mockReset();
  mockedTranscribe.mockReset();
  mockedCaps.mockReset().mockResolvedValue({ stt: true, tts: true });
  push.mockReset();
});

test("VoiceInput démarre et arrête l'enregistrement", async () => {
  const stopTrack = jest.fn();
  const stream = { getTracks: () => [{ stop: stopTrack }] };
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: jest.fn().mockResolvedValue(stream) } });
  const instances: { state: string; start: jest.Mock; stop: jest.Mock; onstop?: () => void }[] = [];
  (global as unknown as { MediaRecorder: unknown }).MediaRecorder = jest.fn().mockImplementation(() => {
    const rec = {
      state: "inactive",
      mimeType: "audio/webm",
      start: jest.fn(function (this: { state: string }) { this.state = "recording"; }),
      stop: jest.fn(function (this: { state: string; onstop?: () => void }) { this.state = "inactive"; this.onstop?.(); }),
      ondataavailable: null,
      onstop: undefined as undefined | (() => void),
    };
    instances.push(rec);
    return rec;
  });

  render(<VoiceInput lang="fr" onTranscript={jest.fn()} />);
  const button = screen.getByRole("button");
  await act(async () => fireEvent.click(button));
  expect(instances[0].start).toHaveBeenCalled();
  expect(button).toHaveAttribute("aria-pressed", "true");

  await act(async () => fireEvent.click(button));
  expect(instances[0].stop).toHaveBeenCalled();
  expect(stopTrack).toHaveBeenCalled();
  await waitFor(() => expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "false"));
});

test("VoiceInput sans Whisper : la reconnaissance du navigateur déclenche la question en fin de phrase", async () => {
  mockedCaps.mockResolvedValue({ stt: false, tts: false });
  const recs: Record<string, unknown>[] = [];
  (window as unknown as { webkitSpeechRecognition: unknown }).webkitSpeechRecognition = jest.fn().mockImplementation(() => {
    const rec = { start: jest.fn(), stop: jest.fn(), abort: jest.fn() } as Record<string, unknown>;
    recs.push(rec);
    return rec;
  });
  const onTranscript = jest.fn();
  render(<VoiceInput lang="darija" onTranscript={onTranscript} />);
  await act(async () => fireEvent.click(screen.getByRole("button")));
  const rec = recs[0] as { lang: string; continuous: boolean; start: jest.Mock; onresult: (e: unknown) => void; onend: () => void };
  expect(rec.start).toHaveBeenCalled();
  expect(rec.lang).toBe("ar-MA");
  expect(rec.continuous).toBe(false);

  // L'usager parle puis se tait : résultat final puis « end », sans aucun clic.
  act(() => rec.onresult({ results: { length: 1, 0: { isFinal: true, length: 1, 0: { transcript: "ضاعت ليا لاكارط" } } } }));
  act(() => rec.onend());
  expect(onTranscript).toHaveBeenCalledWith("ضاعت ليا لاكارط");
  delete (window as unknown as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition;
});

test("Détection de silence : fin du message après la parole, abandon sans parole", () => {
  const vad = new SilenceDetector();
  let now = 0;
  const feed = (level: number, ms: number) => {
    let state = "";
    for (let t = 0; t < ms; t += 50) state = vad.update(level, (now += 50));
    return state;
  };
  expect(feed(0.005, 250)).toBe("calibrating");
  expect(feed(0.2, 800)).toBe("speaking"); // l'usager parle
  expect(feed(0.005, 800)).toBe("speaking"); // courte pause dans la phrase
  expect(feed(0.005, 600)).toBe("stop"); // silence > 1,3 s → envoi automatique
  expect(vad.heardSpeech).toBe(true);

  const quiet = new SilenceDetector();
  let t2 = 0;
  let state = "";
  for (let i = 0; i < 160; i++) state = quiet.update(0.004, (t2 += 50));
  expect(state).toBe("nospeech");
  expect(quiet.heardSpeech).toBe(false);
});

test("Voix : jamais une voix d'une autre langue pour l'arabe / la darija", () => {
  const voices = [
    { lang: "fr-FR", name: "Microsoft Denise" },
    { lang: "en-US", name: "Google US English" },
  ];
  expect(pickVoice(voices, "ar")).toBeNull();
  expect(pickVoice(voices, "darija")).toBeNull();
  const withArabic = [...voices, { lang: "ar-SA", name: "Microsoft Hamed" },
    { lang: "ar-MA", name: "Microsoft Mouna Online (Natural) - Arabic (Morocco)" }];
  expect(pickVoice(withArabic, "darija")?.lang).toBe("ar-MA");
  expect(pickVoice(withArabic, "fr")?.name).toBe("Microsoft Denise");
  expect(toSpeech("75 Dhs · 35x45 mm", "ar")).toBe("75 درهم، 35 × 45 mm");
});

test("TextInput supporte la saisie RTL arabe", () => {
  const onSubmit = jest.fn();
  render(<TextInput lang="ar" onSubmit={onSubmit} />);
  const input = screen.getByRole("textbox");
  expect(input).toHaveAttribute("dir", "rtl");
  expect(screen.getByTestId("virtual-keyboard")).toHaveAttribute("data-rtl", "true");
  fireEvent.change(input, { target: { value: "وثائق البطاقة الوطنية" } });
  fireEvent.submit(input.closest("form")!);
  expect(onSubmit).toHaveBeenCalledWith("وثائق البطاقة الوطنية");
});

test("ResponseDisplay lit les documents à voix haute", async () => {
  const play = jest.fn().mockResolvedValue(undefined);
  (global as unknown as { Audio: unknown }).Audio = jest.fn().mockImplementation(() => ({ play, pause: jest.fn() }));
  const synth = mockedSynthesize.mockResolvedValue({ audio: "AAAA", mime_type: "audio/mpeg" });

  render(<ResponseDisplay result={RESULT} lang="fr" question="Documents CIN" onNewQuestion={jest.fn()} />);
  expect(screen.getByText("Certificat de résidence")).toBeInTheDocument();
  await waitFor(() => expect(synth).toHaveBeenCalledWith(expect.stringContaining("1. Certificat de résidence"), "fr"));
  await waitFor(() => expect(play).toHaveBeenCalled());
  expect(spokenText(RESULT, "fr")).toContain("2. Quatre photographies");
});

test("IdleScreen reset après 30s inactivité", () => {
  jest.useFakeTimers();
  const onIdle = jest.fn();
  render(<IdleScreen onIdle={onIdle}><p>contenu</p></IdleScreen>);
  act(() => jest.advanceTimersByTime(29_000));
  expect(onIdle).not.toHaveBeenCalled();
  act(() => {
    window.dispatchEvent(new Event("touchstart"));
    jest.advanceTimersByTime(29_000);
  });
  expect(onIdle).not.toHaveBeenCalled();
  act(() => jest.advanceTimersByTime(1_500));
  expect(onIdle).toHaveBeenCalledTimes(1);
  jest.useRealTimers();
});

test("Mode hors ligne affiche cache local", async () => {
  const pack: OfflinePack = {
    demarches: [{ slug: "cin-perte-vol-deterioration", langue: "fr", titre: "CNIE — perte, vol ou détérioration", cout_mad: 75,
      source_url: "https://www.cnie.ma/static/procedure", documents: [RESULT.documents[0]] }],
    chunks: [{ demarche_slug: "cin-perte-vol-deterioration", langue: "fr", contenu: "CNIE perte vol détérioration carte perdue déclaration honneur" }],
  };
  const offline = answerOffline("carte perdue perte", "fr", pack);
  expect(offline?.offline).toBe(true);
  expect(offline?.demarche_id).toBe("cin-perte-vol-deterioration");
  expect(answerOffline("météo casablanca demain", "fr", pack)).toBeNull();

  mockedSynthesize.mockRejectedValue(new Error("offline"));
  render(<ResponseDisplay result={offline!} lang="fr" question="carte perdue" onNewQuestion={jest.fn()} />);
  expect(screen.getByText(/Mode hors ligne/)).toBeInTheDocument();
  // Sans ElevenLabs ni voix française dans jsdom : message explicite plutôt qu'une lecture incohérente.
  await waitFor(() => expect(screen.getByText(/Lecture vocale indisponible/)).toBeInTheDocument());
});
