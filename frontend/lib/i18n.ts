export const LANGS = ["darija", "ar", "fr", "en", "pt", "es"] as const;
export type Lang = (typeof LANGS)[number];

export const isLang = (v: string): v is Lang => (LANGS as readonly string[]).includes(v);
export const isRtl = (lang: Lang) => lang === "ar" || lang === "darija";

export const LANG_META: Record<Lang, { native: string; flag: string; htmlLang: string }> = {
  darija: { native: "الدارجة", flag: "🇲🇦", htmlLang: "ar-MA" },
  ar: { native: "العربية", flag: "🇲🇦", htmlLang: "ar" },
  fr: { native: "Français", flag: "🇫🇷", htmlLang: "fr" },
  en: { native: "English", flag: "🇬🇧", htmlLang: "en" },
  pt: { native: "Português", flag: "🇵🇹", htmlLang: "pt" },
  es: { native: "Español", flag: "🇪🇸", htmlLang: "es" },
};

type Key =
  | "welcome" | "chooseLang" | "tapToSpeak" | "listening" | "stop" | "orType" | "useVoice" | "useKeyboard"
  | "send" | "placeholder" | "thinking" | "requiredDocs" | "optional" | "repeat" | "newQuestion" | "print"
  | "cost" | "source" | "scanQr" | "outOfScope" | "offline" | "error" | "micDenied" | "idleTitle" | "idleTouch"
  | "examples" | "back" | "noSpeech" | "noVoice";

export const T: Record<Lang, Record<Key, string>> = {
  fr: {
    welcome: "Bienvenue", chooseLang: "Choisissez votre langue", tapToSpeak: "Touchez le micro et posez votre question",
    listening: "Je vous écoute…", stop: "Arrêter", orType: "ou écrivez", useVoice: "Parler", useKeyboard: "Clavier",
    send: "Envoyer", placeholder: "Ex. : documents pour la carte d'identité", thinking: "Je cherche la réponse…",
    requiredDocs: "Documents à fournir", optional: "facultatif", repeat: "Répéter", newQuestion: "Nouvelle question",
    print: "Imprimer", cost: "Coût", source: "Source officielle", scanQr: "Scannez pour plus d'informations",
    outOfScope: "Rapprochez-vous du guichet", offline: "Mode hors ligne — informations en cache",
    error: "Service momentanément indisponible. Réessayez ou utilisez le clavier.",
    micDenied: "Micro indisponible : utilisez le clavier.", idleTitle: "Votre assistant administratif",
    idleTouch: "Touchez l'écran pour commencer", examples: "Exemples", back: "Langues",
    noSpeech: "Je n'ai rien entendu. Touchez le micro et parlez.",
    noVoice: "Lecture vocale indisponible pour cette langue sur cette borne.",
  },
  ar: {
    welcome: "مرحبا", chooseLang: "اختر لغتك", tapToSpeak: "اضغط على الميكروفون واطرح سؤالك", listening: "أنا أستمع…",
    stop: "إيقاف", orType: "أو اكتب", useVoice: "تحدث", useKeyboard: "لوحة المفاتيح", send: "إرسال",
    placeholder: "مثال: وثائق البطاقة الوطنية", thinking: "أبحث عن الجواب…", requiredDocs: "الوثائق المطلوبة",
    optional: "اختياري", repeat: "إعادة", newQuestion: "سؤال جديد", print: "طباعة", cost: "التكلفة",
    source: "المصدر الرسمي", scanQr: "امسح الرمز لمزيد من المعلومات", outOfScope: "يرجى التوجه إلى الشباك",
    offline: "وضع عدم الاتصال — معلومات محفوظة", error: "الخدمة غير متاحة حاليا. أعد المحاولة أو استعمل لوحة المفاتيح.",
    micDenied: "الميكروفون غير متاح: استعمل لوحة المفاتيح.", idleTitle: "مساعدك الإداري", idleTouch: "المس الشاشة للبدء",
    examples: "أمثلة", back: "اللغات",
    noSpeech: "لم أسمع شيئا. اضغط على الميكروفون وتحدث.",
    noVoice: "القراءة الصوتية غير متاحة لهذه اللغة على هذا الجهاز.",
  },
  darija: {
    welcome: "مرحبا بيك", chooseLang: "ختار اللغة ديالك", tapToSpeak: "ضغط على الميكرو وسول", listening: "كنسمع ليك…",
    stop: "حبس", orType: "ولا كتب", useVoice: "هضر", useKeyboard: "الكلافيي", send: "صيفط",
    placeholder: "مثلا: شنو خاصني باش ندير لاكارط", thinking: "كنقلب على الجواب…", requiredDocs: "الوراق اللي خاصك",
    optional: "ماشي ضروري", repeat: "عاود", newQuestion: "سؤال جديد", print: "طبع", cost: "الثمن",
    source: "المصدر الرسمي", scanQr: "سكاني باش تعرف كتر", outOfScope: "سير للشباك يعاونوك",
    offline: "بلا أنترنيت — معلومات محفوظة", error: "الخدمة ما خدامةش دابا. عاود ولا استعمل الكلافيي.",
    micDenied: "الميكرو ما خدامش: استعمل الكلافيي.", idleTitle: "المساعد الإداري ديالك", idleTouch: "قيس الشاشة باش تبدا",
    examples: "أمثلة", back: "اللغات",
    noSpeech: "ما سمعت والو. ضغط على الميكرو وهضر.",
    noVoice: "القراءة بالصوت ما متوفراش بهاد اللغة فهاد الجهاز.",
  },
  en: {
    welcome: "Welcome", chooseLang: "Choose your language", tapToSpeak: "Tap the microphone and ask your question",
    listening: "Listening…", stop: "Stop", orType: "or type", useVoice: "Speak", useKeyboard: "Keyboard", send: "Send",
    placeholder: "E.g. documents for the ID card", thinking: "Looking for the answer…", requiredDocs: "Required documents",
    optional: "optional", repeat: "Repeat", newQuestion: "New question", print: "Print", cost: "Cost",
    source: "Official source", scanQr: "Scan for more information", outOfScope: "Please visit the service desk",
    offline: "Offline mode — cached information", error: "Service temporarily unavailable. Try again or use the keyboard.",
    micDenied: "Microphone unavailable: use the keyboard.", idleTitle: "Your administrative assistant",
    idleTouch: "Touch the screen to start", examples: "Examples", back: "Languages",
    noSpeech: "I didn't hear anything. Tap the microphone and speak.",
    noVoice: "Voice playback is not available for this language on this kiosk.",
  },
  pt: {
    welcome: "Bem-vindo", chooseLang: "Escolha o seu idioma", tapToSpeak: "Toque no microfone e faça a sua pergunta",
    listening: "Estou a ouvir…", stop: "Parar", orType: "ou escreva", useVoice: "Falar", useKeyboard: "Teclado", send: "Enviar",
    placeholder: "Ex.: documentos para o cartão de identidade", thinking: "A procurar a resposta…",
    requiredDocs: "Documentos exigidos", optional: "opcional", repeat: "Repetir", newQuestion: "Nova pergunta",
    print: "Imprimir", cost: "Custo", source: "Fonte oficial", scanQr: "Digitalize para mais informações",
    outOfScope: "Dirija-se ao balcão", offline: "Modo offline — informação em cache",
    error: "Serviço temporariamente indisponível. Tente novamente ou use o teclado.",
    micDenied: "Microfone indisponível: use o teclado.", idleTitle: "O seu assistente administrativo",
    idleTouch: "Toque no ecrã para começar", examples: "Exemplos", back: "Idiomas",
    noSpeech: "Não ouvi nada. Toque no microfone e fale.",
    noVoice: "Leitura por voz indisponível para este idioma neste terminal.",
  },
  es: {
    welcome: "Bienvenido", chooseLang: "Elija su idioma", tapToSpeak: "Toque el micrófono y haga su pregunta",
    listening: "Le escucho…", stop: "Detener", orType: "o escriba", useVoice: "Hablar", useKeyboard: "Teclado", send: "Enviar",
    placeholder: "Ej.: documentos para el carné de identidad", thinking: "Buscando la respuesta…",
    requiredDocs: "Documentos requeridos", optional: "opcional", repeat: "Repetir", newQuestion: "Nueva pregunta",
    print: "Imprimir", cost: "Coste", source: "Fuente oficial", scanQr: "Escanee para más información",
    outOfScope: "Diríjase a la ventanilla", offline: "Modo sin conexión — información en caché",
    error: "Servicio no disponible temporalmente. Inténtelo de nuevo o use el teclado.",
    micDenied: "Micrófono no disponible: use el teclado.", idleTitle: "Su asistente administrativo",
    idleTouch: "Toque la pantalla para empezar", examples: "Ejemplos", back: "Idiomas",
    noSpeech: "No he oído nada. Toque el micrófono y hable.",
    noVoice: "Lectura por voz no disponible para este idioma en este terminal.",
  },
};

export const EXAMPLES: Record<Lang, string[]> = {
  fr: ["Documents pour une première carte d'identité", "J'ai perdu ma carte d'identité", "Carte d'identité pour mon enfant"],
  ar: ["ما هي وثائق البطاقة الوطنية لأول مرة؟", "وثائق تجديد البطاقة الوطنية", "ضاعت بطاقتي الوطنية"],
  darija: ["شنو خاصني باش ندير لاكارط أول مرة؟", "ضاعت ليا لاكارط", "بغيت ندير لاكارط لولدي"],
  en: ["Documents for a first ID card", "I lost my ID card", "How do I renew my ID card?"],
  pt: ["Documentos para o primeiro cartão de identidade", "Perdi o meu cartão de identidade", "Como renovar o cartão?"],
  es: ["Documentos para el primer carné de identidad", "He perdido mi carné de identidad", "¿Cómo renovar el carné?"],
};
