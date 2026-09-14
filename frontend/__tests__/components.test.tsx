import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import IdleScreen from "@/components/IdleScreen";
import ResponseDisplay, { spokenText } from "@/components/ResponseDisplay";
import TextInput from "@/components/TextInput";
import VoiceInput from "@/components/VoiceInput";
import * as api from "@/lib/api";
import { answerOffline, type OfflinePack } from "@/lib/offline";

jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  synthesize: jest.fn(),
  transcribe: jest.fn(),
}));
const mockedSynthesize = api.synthesize as jest.MockedFunction<typeof api.synthesize>;

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

test("Mode hors ligne affiche cache local", () => {
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
});
