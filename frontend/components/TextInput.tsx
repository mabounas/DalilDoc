"use client";

import { useRef, useState } from "react";
import Keyboard from "react-simple-keyboard";
import { isRtl, T, type Lang } from "@/lib/i18n";

const LAYOUTS = {
  latin: {
    default: ["1 2 3 4 5 6 7 8 9 0 {bksp}", "a z e r t y u i o p", "q s d f g h j k l m", "w x c v b n ' é è à", "{space} ? {enter}"],
  },
  latinQwerty: {
    default: ["1 2 3 4 5 6 7 8 9 0 {bksp}", "q w e r t y u i o p", "a s d f g h j k l ñ", "z x c v b n m ç ã ?", "{space} {enter}"],
  },
  arabic: {
    default: ["١ ٢ ٣ ٤ ٥ ٦ ٧ ٨ ٩ ٠ {bksp}", "ض ص ث ق ف غ ع ه خ ح ج", "ش س ي ب ل ا ت ن م ك ط", "ئ ء ؤ ر ى ة و ز ظ د ذ", "{space} ؟ {enter}"],
  },
};

interface Props {
  lang: Lang;
  onSubmit: (text: string) => void;
}

/** Saisie tactile avec clavier virtuel ; direction RTL pour l'arabe et la darija. */
export default function TextInput({ lang, onSubmit }: Props) {
  const t = T[lang];
  const rtl = isRtl(lang);
  const [value, setValue] = useState("");
  const keyboardRef = useRef<{ setInput: (v: string) => void } | null>(null);
  const layout = rtl ? LAYOUTS.arabic : lang === "fr" ? LAYOUTS.latin : LAYOUTS.latinQwerty;

  const submit = () => {
    if (!value.trim()) return;
    onSubmit(value.trim());
    setValue("");
    keyboardRef.current?.setInput("");
  };

  return (
    <form
      className="flex w-full flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <div className="flex gap-3">
        <input
          aria-label={t.placeholder}
          dir={rtl ? "rtl" : "ltr"}
          lang={lang === "darija" ? "ar-MA" : lang}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            keyboardRef.current?.setInput(e.target.value);
          }}
          placeholder={t.placeholder}
          maxLength={500}
          className="min-h-touch flex-1 rounded-2xl border-2 border-night-600 bg-night-800 px-5 text-xl text-ink placeholder:text-ink-muted focus:border-gold"
        />
        <button type="submit" className="min-h-touch min-w-touch rounded-2xl bg-gold px-6 text-xl font-semibold text-night active:bg-gold-light">
          {t.send}
        </button>
      </div>
      <div dir="ltr" className="no-print">
        <Keyboard
          keyboardRef={(r: { setInput: (v: string) => void }) => (keyboardRef.current = r)}
          layout={layout}
          display={{ "{bksp}": "⌫", "{enter}": t.send, "{space}": " " }}
          onChange={(input: string) => setValue(input)}
          onKeyPress={(button: string) => button === "{enter}" && submit()}
          rtl={rtl}
        />
      </div>
    </form>
  );
}
