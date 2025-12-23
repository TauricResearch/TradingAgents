/**
 * i18n exports and utilities
 */
import { en, TranslationKeys } from './en';
import { zhTW } from './zh-TW';

export type Locale = 'en' | 'zh-TW';

export const translations: Record<Locale, TranslationKeys> = {
  'en': en,
  'zh-TW': zhTW,
};

export const localeNames: Record<Locale, string> = {
  'en': 'English',
  'zh-TW': '繁體中文',
};

export const defaultLocale: Locale = 'zh-TW';

export { en, zhTW };
export type { TranslationKeys };
