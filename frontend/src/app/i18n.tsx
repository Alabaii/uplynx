import React, { createContext, useContext, useEffect, useState } from 'react';

export type Lang = 'ru' | 'en';

const STORAGE_KEY = 'uplynx.lang';

function initialLang(): Lang {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'en' || stored === 'ru') {
      return stored;
    }
  } catch {
    // приватный режим/запрещённый storage — просто дефолт
  }
  return 'ru';
}

const LangContext = createContext<{ lang: Lang; setLang: (lang: Lang) => void }>({
  lang: 'ru',
  setLang: () => {},
});

// Текущий язык для НЕ-компонентного кода (utils/time.ts): хуки там недоступны.
// Обновляется провайдером; смена языка перерисовывает всё дерево через контекст,
// так что функции, читающие activeLang во время рендера, всегда видят актуальное значение.
let activeLang: Lang = initialLang();

export function getActiveLang(): Lang {
  return activeLang;
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);

  const setLang = (next: Lang) => {
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // недоступный storage не мешает переключению в рамках сессии
    }
    setLangState(next);
  };

  useEffect(() => {
    document.documentElement.lang = lang;
    activeLang = lang;
  }, [lang]);

  return <LangContext.Provider value={{ lang, setLang }}>{children}</LangContext.Provider>;
}

export function useLang() {
  return useContext(LangContext);
}

/**
 * Строки компонента парой ru/en рядом с разметкой. Тип выводится из ru,
 * а `en: T` заставляет TypeScript следить, что наборы ключей совпадают.
 *
 *   const t = useTexts({
 *     ru: { title: 'Мониторы', added: (n: number) => `Добавлено: ${n}` },
 *     en: { title: 'Monitors', added: (n: number) => `Added: ${n}` },
 *   });
 */
export function useTexts<T>(texts: { ru: T; en: T }): T {
  return texts[useLang().lang];
}

/** Подписи статусов монитора — общие для страниц: const labels = useTexts(monitorStatusTexts). */
export const monitorStatusTexts = {
  ru: { up: 'Работает', down: 'Недоступен', paused: 'На паузе', degraded: 'Деградация', pending: 'Ожидание' },
  en: { up: 'Up', down: 'Down', paused: 'Paused', degraded: 'Degraded', pending: 'Pending' },
};

/** Русские множественные формы: plural(n, ['монитор', 'монитора', 'мониторов']). */
export function plural(n: number, forms: [string, string, string]): string {
  const abs = Math.abs(n) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return forms[2];
  if (last > 1 && last < 5) return forms[1];
  if (last === 1) return forms[0];
  return forms[2];
}

export function LanguageSwitcher({ className }: { className?: string }) {
  const { lang, setLang } = useLang();
  const base = 'rounded px-1.5 py-0.5 text-[11px] font-semibold transition-colors';
  return (
    <div
      className={`inline-flex items-center gap-0.5 rounded-lg bg-card p-1 shadow-card ${className ?? ''}`}
      role="group"
      aria-label="Language"
    >
      {(['ru', 'en'] as const).map((code) => (
        <button
          key={code}
          type="button"
          onClick={() => setLang(code)}
          aria-pressed={lang === code}
          className={`${base} ${lang === code ? 'bg-accent text-primary' : 'text-muted-foreground hover:text-primary'}`}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
