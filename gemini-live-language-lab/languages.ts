import { Language, LanguageInfo } from './types';

export const LANGUAGES: LanguageInfo[] = [
  // Spanish Variants
  {
    code: Language.SPANISH_SPAIN,
    name: 'Spanish (Spain)',
    nativeName: 'Español (España)',
    flag: '🇪🇸'
  },
  {
    code: Language.SPANISH_MEXICO,
    name: 'Spanish (Mexico)',
    nativeName: 'Español (México)',
    flag: '🇲🇽'
  },
  {
    code: Language.SPANISH_ARGENTINA,
    name: 'Spanish (Argentina)',
    nativeName: 'Español (Argentina)',
    flag: '🇦🇷'
  },
  {
    code: Language.SPANISH_COLOMBIA,
    name: 'Spanish (Colombia)',
    nativeName: 'Español (Colombia)',
    flag: '🇨🇴'
  },
  
  // English Variants
  {
    code: Language.ENGLISH_US,
    name: 'English (US)',
    nativeName: 'English (US)',
    flag: '🇺🇸'
  },
  {
    code: Language.ENGLISH_UK,
    name: 'English (UK)',
    nativeName: 'English (UK)',
    flag: '🇬🇧'
  },
  {
    code: Language.ENGLISH_AUSTRALIA,
    name: 'English (Australia)',
    nativeName: 'English (Australia)',
    flag: '🇦🇺'
  },
  {
    code: Language.ENGLISH_CANADA,
    name: 'English (Canada)',
    nativeName: 'English (Canada)',
    flag: '🇨🇦'
  },
  
  // Other Major Languages
  {
    code: Language.FRENCH,
    name: 'French',
    nativeName: 'Français',
    flag: '🇫🇷'
  },
  {
    code: Language.GERMAN,
    name: 'German',
    nativeName: 'Deutsch',
    flag: '🇩🇪'
  },
  {
    code: Language.ITALIAN,
    name: 'Italian',
    nativeName: 'Italiano',
    flag: '🇮🇹'
  },
  {
    code: Language.PORTUGUESE,
    name: 'Portuguese (Brazil)',
    nativeName: 'Português (Brasil)',
    flag: '🇧🇷'
  },
  {
    code: Language.CHINESE_MANDARIN,
    name: 'Chinese (Mandarin)',
    nativeName: '中文',
    flag: '🇨🇳'
  },
  {
    code: Language.JAPANESE,
    name: 'Japanese',
    nativeName: '日本語',
    flag: '🇯🇵'
  },
  {
    code: Language.KOREAN,
    name: 'Korean',
    nativeName: '한국어',
    flag: '🇰🇷'
  },
  {
    code: Language.ARABIC,
    name: 'Arabic',
    nativeName: 'العربية',
    flag: '🇸🇦'
  },
  {
    code: Language.HINDI,
    name: 'Hindi',
    nativeName: 'हिन्दी',
    flag: '🇮🇳'
  },
  {
    code: Language.DUTCH,
    name: 'Dutch',
    nativeName: 'Nederlands',
    flag: '🇳🇱'
  },
  {
    code: Language.RUSSIAN,
    name: 'Russian',
    nativeName: 'Русский',
    flag: '🇷🇺'
  },
  {
    code: Language.SWEDISH,
    name: 'Swedish',
    nativeName: 'Svenska',
    flag: '🇸🇪'
  },
  {
    code: Language.NORWEGIAN,
    name: 'Norwegian',
    nativeName: 'Norsk',
    flag: '🇳🇴'
  },
  {
    code: Language.DANISH,
    name: 'Danish',
    nativeName: 'Dansk',
    flag: '🇩🇰'
  },
  {
    code: Language.FINNISH,
    name: 'Finnish',
    nativeName: 'Suomi',
    flag: '🇫🇮'
  },
  {
    code: Language.POLISH,
    name: 'Polish',
    nativeName: 'Polski',
    flag: '🇵🇱'
  },
  {
    code: Language.TURKISH,
    name: 'Turkish',
    nativeName: 'Türkçe',
    flag: '🇹🇷'
  },
  {
    code: Language.GREEK,
    name: 'Greek',
    nativeName: 'Ελληνικά',
    flag: '🇬🇷'
  },
  {
    code: Language.HEBREW,
    name: 'Hebrew',
    nativeName: 'עברית',
    flag: '🇮🇱'
  },
  {
    code: Language.THAI,
    name: 'Thai',
    nativeName: 'ไทย',
    flag: '🇹🇭'
  },
  {
    code: Language.VIETNAMESE,
    name: 'Vietnamese',
    nativeName: 'Tiếng Việt',
    flag: '🇻🇳'
  },
  {
    code: Language.INDONESIAN,
    name: 'Indonesian',
    nativeName: 'Bahasa Indonesia',
    flag: '🇮🇩'
  }
];

export const getLanguageByCode = (code: Language): LanguageInfo | undefined => {
  return LANGUAGES.find(lang => lang.code === code);
};

export const getSpanishVariants = (): LanguageInfo[] => {
  return LANGUAGES.filter(lang => lang.code.startsWith('es-'));
};

export const getPopularLanguages = (): LanguageInfo[] => {
  return [
    getLanguageByCode(Language.SPANISH_SPAIN)!,
    getLanguageByCode(Language.ENGLISH_US)!,
    getLanguageByCode(Language.FRENCH)!,
    getLanguageByCode(Language.GERMAN)!,
    getLanguageByCode(Language.ITALIAN)!,
    getLanguageByCode(Language.PORTUGUESE)!,
    getLanguageByCode(Language.CHINESE_MANDARIN)!,
    getLanguageByCode(Language.JAPANESE)!,
  ];
};
