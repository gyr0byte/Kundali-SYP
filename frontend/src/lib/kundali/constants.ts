import type { ChartSettings } from "./types";

export interface SignDescriptor {
  index: number;
  en: string;
  rashiEn: string;
  ne: string;
  shortEn: string;
  shortNe: string;
}

export const ZODIAC_SIGNS: readonly SignDescriptor[] = [
  { index: 0, en: "Aries", rashiEn: "Mesha", ne: "मेष", shortEn: "Ari", shortNe: "मेष" },
  { index: 1, en: "Taurus", rashiEn: "Vrishabha", ne: "वृषभ", shortEn: "Tau", shortNe: "वृष" },
  { index: 2, en: "Gemini", rashiEn: "Mithun", ne: "मिथुन", shortEn: "Gem", shortNe: "मिथु" },
  { index: 3, en: "Cancer", rashiEn: "Karkat", ne: "कर्कट", shortEn: "Can", shortNe: "कर्क" },
  { index: 4, en: "Leo", rashiEn: "Singh", ne: "सिंह", shortEn: "Leo", shortNe: "सिंह" },
  { index: 5, en: "Virgo", rashiEn: "Kanya", ne: "कन्या", shortEn: "Vir", shortNe: "कन्या" },
  { index: 6, en: "Libra", rashiEn: "Tula", ne: "तुला", shortEn: "Lib", shortNe: "तुला" },
  { index: 7, en: "Scorpio", rashiEn: "Vrishchika", ne: "वृश्चिक", shortEn: "Sco", shortNe: "वृश्चि" },
  { index: 8, en: "Sagittarius", rashiEn: "Dhanu", ne: "धनु", shortEn: "Sag", shortNe: "धनु" },
  { index: 9, en: "Capricorn", rashiEn: "Makar", ne: "मकर", shortEn: "Cap", shortNe: "मकर" },
  { index: 10, en: "Aquarius", rashiEn: "Kumbha", ne: "कुम्भ", shortEn: "Aqu", shortNe: "कुम्भ" },
  { index: 11, en: "Pisces", rashiEn: "Meen", ne: "मीन", shortEn: "Pis", shortNe: "मीन" },
] as const;

export const PLANET_LABELS: Record<
  string,
  { en: string; ne: string; glyphEn: string; glyphNe: string }
> = {
  Lagna: { en: "Lagna (Asc)", ne: "लग्न", glyphEn: "Asc", glyphNe: "ल" },
  Sun: { en: "Sun (Surya)", ne: "सूर्य", glyphEn: "Su", glyphNe: "सू" },
  Moon: { en: "Moon (Chandra)", ne: "चन्द्र", glyphEn: "Mo", glyphNe: "च" },
  Mars: { en: "Mars (Mangal)", ne: "मंगल", glyphEn: "Ma", glyphNe: "मं" },
  Mercury: { en: "Mercury (Budha)", ne: "बुध", glyphEn: "Me", glyphNe: "बु" },
  Jupiter: { en: "Jupiter (Guru)", ne: "बृहस्पति", glyphEn: "Ju", glyphNe: "बृ" },
  Venus: { en: "Venus (Shukra)", ne: "शुक्र", glyphEn: "Ve", glyphNe: "शु" },
  Saturn: { en: "Saturn (Shani)", ne: "शनि", glyphEn: "Sa", glyphNe: "श" },
  Rahu: { en: "Rahu", ne: "राहु", glyphEn: "Ra", glyphNe: "रा" },
  Ketu: { en: "Ketu", ne: "केतु", glyphEn: "Ke", glyphNe: "के" },
};

export const NAKSHATRA_NE: Record<string, string> = {
  Ashwini: "अश्विनी",
  Bharani: "भरणी",
  Krittika: "कृत्तिका",
  Rohini: "रोहिणी",
  Mrigashira: "मृगशिरा",
  Ardra: "आर्द्रा",
  Punarvasu: "पुनर्वसु",
  Pushya: "पुष्य",
  Ashlesha: "अश्लेषा",
  Magha: "मघा",
  "Purva Phalguni": "पूर्वफाल्गुनी",
  "Uttara Phalguni": "उत्तरफाल्गुनी",
  Hasta: "हस्त",
  Chitra: "चित्रा",
  Swati: "स्वाती",
  Vishakha: "विशाखा",
  Anuradha: "अनुराधा",
  Jyeshtha: "ज्येष्ठा",
  Mula: "मूल",
  "Purva Ashadha": "पूर्वाषाढा",
  "Uttara Ashadha": "उत्तराषाढा",
  Shravana: "श्रवण",
  Dhanishta: "धनिष्ठा",
  Shatabhisha: "शतभिषा",
  "Purva Bhadrapada": "पूर्वभाद्रपद",
  "Uttara Bhadrapada": "उत्तरभाद्रपद",
  Revati: "रेवती",
};

export const AYANAMSHA_OPTIONS = [
  { value: "lahiri", labelEn: "Lahiri (Chitrapaksha)", labelNe: "लाहिरी (चित्रपक्ष)" },
  { value: "lahiri_1940", labelEn: "Lahiri 1940", labelNe: "लाहिरी १९४०" },
  { value: "raman", labelEn: "B.V. Raman", labelNe: "रमण" },
  { value: "krishnamurti", labelEn: "Krishnamurti (KP)", labelNe: "कृष्णमूर्ति (KP)" },
] as const;

export const NODE_TYPE_OPTIONS = [
  { value: "mean", labelEn: "Mean Node", labelNe: "मध्य राहु/केतु (Mean)" },
  { value: "true", labelEn: "True Node", labelNe: "स्पष्ट राहु/केतु (True)" },
] as const;

export const YEAR_DAYS_OPTIONS = [
  { value: 365.25, labelEn: "365.25 days (Julian year)", labelNe: "३६५.२५ दिन" },
  { value: 360, labelEn: "360 days (Savana year)", labelNe: "३६० दिन (सावन वर्ष)" },
  { value: 365.2425, labelEn: "365.2425 days (Gregorian)", labelNe: "३६५.२४२५ दिन" },
] as const;

export const HAMRO_PATRO_COMPAT_PRESET: ChartSettings = {
  ayanamsha: "lahiri_1940",
  house_system: "whole_sign",
  node_type: "true",
  year_days: 365.25,
  preset: "hamro_patro_compat",
};

export const COMMON_TIMEZONES = [
  "Asia/Kathmandu",
  "Asia/Kolkata",
  "Europe/London",
  "America/New_York",
  "Asia/Tokyo",
  "Australia/Sydney",
  "UTC",
] as const;
