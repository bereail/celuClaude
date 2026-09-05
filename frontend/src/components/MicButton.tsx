import { useRef, useState } from "react";

interface Props {
  onResult: (text: string) => void;
  disabled?: boolean;
}

// Web Speech API no tiene tipos oficiales en TS/DOM todavia.
type SpeechRecognitionInstance = any;

export function MicButton({ onResult, disabled }: Props) {
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);

  const SpeechRecognitionCtor =
    (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

  const start = () => {
    if (disabled || !SpeechRecognitionCtor) return;
    const recognition: SpeechRecognitionInstance = new SpeechRecognitionCtor();
    recognition.lang = "es-AR";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event: any) => {
      const text = event.results[0]?.[0]?.transcript;
      if (text) onResult(text);
    };
    recognition.onerror = () => setListening(false);
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  };

  const stop = () => {
    recognitionRef.current?.stop();
    setListening(false);
  };

  if (!SpeechRecognitionCtor) {
    return (
      <button
        disabled
        title="Este navegador no soporta reconocimiento de voz"
        className="h-14 w-14 rounded-full bg-panel text-slate-500 flex items-center justify-center text-2xl"
      >
        🎙️
      </button>
    );
  }

  return (
    <button
      onPointerDown={start}
      onPointerUp={stop}
      onPointerLeave={stop}
      disabled={disabled}
      className={`h-14 w-14 rounded-full flex items-center justify-center text-2xl transition-colors select-none ${
        listening ? "bg-accent animate-pulse" : "bg-panel"
      } ${disabled ? "opacity-40" : ""}`}
    >
      🎙️
    </button>
  );
}
