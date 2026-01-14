export enum VoiceName {
  ZEPHYR = 'Zephyr',
  PUCK = 'Puck',
  CHARON = 'Charon',
  KORE = 'Kore',
  FENRIR = 'Fenrir'
}

export enum Language {
  // Spanish Variants
  SPANISH_SPAIN = 'es-ES',
  SPANISH_MEXICO = 'es-MX',
  SPANISH_ARGENTINA = 'es-AR',
  SPANISH_COLOMBIA = 'es-CO',
  
  // English Variants
  ENGLISH_US = 'en-US',
  ENGLISH_UK = 'en-GB',
  ENGLISH_AUSTRALIA = 'en-AU',
  ENGLISH_CANADA = 'en-CA',
  
  // Other Major Languages
  FRENCH = 'fr-FR',
  GERMAN = 'de-DE',
  ITALIAN = 'it-IT',
  PORTUGUESE = 'pt-BR',
  CHINESE_MANDARIN = 'zh-CN',
  JAPANESE = 'ja-JP',
  KOREAN = 'ko-KR',
  ARABIC = 'ar-SA',
  HINDI = 'hi-IN',
  DUTCH = 'nl-NL',
  RUSSIAN = 'ru-RU',
  SWEDISH = 'sv-SE',
  NORWEGIAN = 'no-NO',
  DANISH = 'da-DK',
  FINNISH = 'fi-FI',
  POLISH = 'pl-PL',
  TURKISH = 'tr-TR',
  GREEK = 'el-GR',
  HEBREW = 'he-IL',
  THAI = 'th-TH',
  VIETNAMESE = 'vi-VN',
  INDONESIAN = 'id-ID'
}

export interface LanguageInfo {
  code: Language;
  name: string;
  nativeName: string;
  flag: string;
}

export type CEFRLevel = 'A1' | 'A2' | 'B1' | 'B2' | 'C1' | 'C2';

export interface ScenarioPARTS {
  persona: string;
  act: string;
  recipient: string;
  theme: string;
  structure: string;
}

export interface TranscriptionEntry {
  role: 'user' | 'model';
  text: string;
  timestamp: number;
}

export interface ConnectionStatus {
  isConnected: boolean;
  isConnecting: boolean;
  error: string | null;
}

export type AppStage = 'setup' | 'calling' | 'active' | 'summary';
