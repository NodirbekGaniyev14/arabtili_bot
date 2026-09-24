export interface PlanData {
  level: string;
  level_reason: string;
  target_level: string;
  target_date: string;
  daily_xp_goal: number;
  daily_minutes: number;
  focus_areas: string[];
  module_order: string[];
  weekly_schedule: { day: number; tasks: string[] }[];
  motivation: string;
  /** Daraja qaysi versiyadagi placement testi bilan aniqlangan */
  placement_version: number;
  /** Joriy placement versiyasi — undan past bo'lsa qayta test so'raladi */
  placement_current: number;
  /** K22.1: onboarding tugagach darhol ochiladigan dars */
  start_lesson?: string;
}

export interface NextLesson {
  id: string;
  title: string;
  module_title: string;
  module_ar: string;
  pos: number;
  count: number;
}

export interface Stats {
  streak: number;
  /** Qolgan streak muzlatkichlari (haftada +1, ko'pi bilan 2) */
  streak_freezes: number;
  xp_today: number;
  words: number;
  lessons: number;
  accuracy: number;
  due_count: number;
  next_lesson: NextLesson | null;
  /** K19.1: oxirgi 7 kun (eskidan bugunga) — bosh sahifa diagrammasi */
  week?: WeekDay[];
  /** K19.1: «Bugun» ro'yxati bayroqlari — haqiqiy faollikdan */
  today?: TodayFlags;
}

export interface WeekDay {
  day: string;
  xp: number;
  lessons: number;
  speaking: number;
}

export interface TodayFlags {
  lesson_done: boolean;
  review_done: boolean;
  speaking_done: boolean;
  new_words: number;
  new_words_goal: number;
}

export interface ReviewCard {
  id: number;
  ar: string;
  translit: string;
  uz: string;
  audio: string;
  kind: "letter" | "word" | "phrase";
}

export type ReviewGrade = "again" | "hard" | "good" | "easy";

export interface MeResponse {
  name: string;
  has_plan: boolean;
  plan: PlanData | null;
  stats: Stats;
  /** VIP tarif (AI ustoz) faolmi */
  vip: boolean;
  vip_days_left: number;
  /** Yorliqlar uchun narx: oylik va kunlik (so'm) */
  vip_price: { month: number; per_day: number };
  /** Kunlik speaking savoli: bajarildimi, streak */
  daily?: { done: boolean; streak: number; best: number; total: number };
  /** K19.2 yozuv mashqi (2 kunda bir matn): bosh sahifa vazifasi */
  writing?: { period: string; title: string; kind: string; done: boolean; score: number };
  /** K20.4 yangi foydalanuvchi: «Jamal bilan tanishing» kartasi */
  intro_pending?: boolean;
  intro_topic?: string;
}

// ── Yozuv (xattotlik) mashqi (K19.2) ──
export interface WritingText {
  id: string;
  kind: string;
  title_uz: string;
  ar: string;
  translit: string;
  uz: string;
  hint_uz: string;
  audio_url: string;
}

export interface WritingFeedback {
  is_handwriting: boolean;
  read_ar: string;
  missing_words: string[];
  wrong_words: { written: string; correct: string; note_uz: string }[];
  tips_uz: string[];
  praise_uz: string;
}

export interface WritingDone extends WritingFeedback {
  score: number;
  neatness: number;
  attempts: number;
  attempts_left: number;
  xp: number;
  best: number;
}

/** K22.4 «Yangi so'zlarim» — kunlar bo'yicha */
export interface RecentWord {
  ar: string;
  translit: string;
  uz: string;
  audio: string;
  kind: string;
}
export interface RecentWordsDay {
  day: string;
  words: RecentWord[];
}

/** K21.5 ulashish kartasi */
export interface ShareCardInfo {
  url: string;
  path: string;
  sent: boolean;
  caption: string;
  ref_link: string;
  streak: number;
  week_xp: number;
}

/** K21.6 harf chizish mashqi */
export interface TraceLetter {
  ar: string;
  name: string;
  uz: string;
  audio: string;
  audio_text: string;
}
export interface TraceInfo {
  letters: TraceLetter[];
  best: Record<string, number>;
  pass: number;
  min_letters: number;
  xp_today: boolean;
}
export interface TraceFinish {
  avg: number;
  count: number;
  xp: number;
  best: Record<string, number>;
  new_badges?: Badge[];
}

export interface WritingInfo {
  period: string;
  ends: string;
  level: string;
  text: WritingText;
  done: WritingDone | null;
  attempts_left: number;
  max_attempts: number;
  history: { period: string; text_id: string; title: string; score: number; neatness: number; xp: number }[];
  ai: boolean;
}

export interface WritingCheck extends WritingDone {
  result: WritingFeedback & { accuracy: number; neatness: number };
  improved: boolean;
  xp_awarded: number;
  new_badges?: Badge[];
}

// ── Kunlik speaking savoli (bepul) ──
export interface DailyResult {
  score: number;
  xp: number;
  voice: boolean;
  answer: string;
  feedback_uz: string;
  ideal_ar: string;
  fixed_ar: string;
}

export interface DailyInfo {
  day: string;
  level: string;
  question: { id: string; ar: string; translit: string; uz: string; hint_uz: string; audio_url: string };
  done: DailyResult | null;
  streak: number;
  best: number;
  total: number;
  ai: boolean;
  voice: boolean;
}

export interface OnboardingPayload {
  name: string;
  goal: string;
  self_level: string;
  target: string;
  duration: string;
  focus: string[];
  daily_minutes: number;
  test: Record<string, unknown>;
}

export interface LessonMeta {
  id: string;
  title: string;
  done: boolean;
  unlocked: boolean;
}

export interface ModuleInfo {
  id: string;
  title: string;
  arabic_title: string;
  available: boolean;
  done_count: number;
  total: number;
  lessons: LessonMeta[];
}

export interface LevelSection {
  level: string;
  name: string;
  available: boolean;
  done: number;
  total: number;
  percent: number;
  modules: ModuleInfo[];
}

export interface LevelsResponse {
  current_level: string;
  levels: LevelSection[];
}

export interface NewItem {
  kind: "letter" | "word" | "phrase";
  ar: string;
  translit: string;
  uz: string;
  audio?: string;
}

export interface Exercise {
  type: "choice" | "listen" | "match" | "assemble" | "type";
  prompt: string;
  arabic?: string;
  audio?: string;
  options?: string[]; // birinchisi to'g'ri (player aralashtiradi)
  pairs?: [string, string][];
  words?: string[];
  extra?: string[];
  answers?: string[];
}

export interface LessonData {
  id: string;
  title: string;
  new_items: NewItem[];
  exercises: Exercise[];
  module_title: string;
  pos: number;
  count: number;
}

export interface Badge {
  id: string;
  icon: string;
  title: string;
  desc: string;
  earned?: boolean;
}

export interface CompleteResponse {
  xp_earned: number;
  perfect: boolean;
  first_time: boolean;
  stats: Stats;
  new_badges: Badge[];
}

export interface League {
  id: string;
  name: string;
  icon: string;
  min_xp: number;
}

export interface LeaderboardEntry {
  rank: number;
  name: string;
  xp: number;
  /** Foydalanuvchining joriy darajasi (A0/A1/A2/B1) */
  level: string;
  /** Ketma-ket faol kunlar */
  streak: number;
  is_me: boolean;
  is_demo: boolean;
  /** VIP obuna faol — reytingda 👑 belgisi (hamma ko'radi) */
  vip?: boolean;
}

export type LeaderPeriod = "week" | "month" | "all";

export interface LeaderboardData {
  period: LeaderPeriod;
  league: League;
  all_leagues: League[];
  my_rank: number;
  my_weekly_xp: number;
  my_period_xp: number;
  entries: LeaderboardEntry[];
}

/** Ma'lumotnoma — grammatika va lug'at */
export interface ReferenceStats {
  grammar_points: number;
  vocab_words: number;
}

export interface GrammarEntry {
  lesson_id: string;
  level: string;
  module: string;
  lesson_title: string;
  point_ar: string;
  explanation_uz: string;
  table: { ar: string; uz: string; form?: string }[];
  common_mistakes_uz: string[];
}

export interface VocabEntry {
  ar: string;
  translit: string;
  uz: string;
  root: string;
  pattern: string;
  pos: string;
  audio: string;
  example_ar: string;
  example_uz: string;
  level: string;
  lessons: string[];
}

/** Lug'at bo'limi (K16) — 6000 so'z, darajalar kesimida */
export interface VocabWord {
  id: string;
  rank: number;
  ar: string;
  translit: string;
  uz: string;
  pos: string;
  root: string;
  pattern: string;
  theme: string;
  level: string;
  example_ar: string;
  example_uz: string;
  audio: string;
  note_uz: string;
  plural_ar?: string;
  past_ar?: string;
  present_ar?: string;
  masdar_ar?: string;
  form?: string;
  lessons: string[];
  source: "lesson" | "vocab";
}

export interface VocabLevelStat {
  level: string;
  total: number;
  target: number;
  learned: number;
}

export interface VocabStats {
  total: number;
  goal: number;
  learned: number;
  levels: VocabLevelStat[];
}

export interface VocabTheme {
  slug: string;
  title_uz: string;
  total: number;
}

/** K25 Oktagon — 1v1 lug'at jangi (REST qismi; jang o'zi — lib/battle.ts WebSocket) */
export interface BattleLeague {
  id: string;
  title: string;
  icon: string;
  next_title: string;
  next_at: number;
}
export interface BattleMe {
  name: string;
  points: number;
  league: BattleLeague;
  games: number;
  wins: number;
  rank: number;
  level: string;
  today: number;
  /** 0 — cheksiz (VIP) */
  daily_limit: number;
  vip: boolean;
  online: number;
  levels: string[];
  rules: { questions: number; seconds: number; bot_wait: number };
}
export interface BattleTopItem {
  rank: number;
  user_id: number;
  name: string;
  points: number;
  wins: number;
  games: number;
  league: BattleLeague;
}
export interface BattleHistoryItem {
  id: number;
  level: string;
  opp: string;
  bot: boolean;
  you: number;
  them: number;
  result: "win" | "lose" | "draw";
  forfeit: boolean;
  delta: number;
  at: string;
}

/** K25.3 — Oktagon mavsumi (oylik) va haftalik reyting (sovrin yo'q) */
export interface BattleWeekRow {
  rank: number;
  user_id: number;
  name: string;
  points: number;
  games: number;
  wins: number;
}
export interface BattleAwardRow {
  rank: number;
  name: string;
  points: number;
  games: number;
  wins: number;
  period_key: string;
}
export interface BattleSeasonData {
  season: { key: string; label: string; days_left: number; ends_at: string; keep_pct: number };
  week: {
    label: string;
    hours_left: number;
    top: BattleWeekRow[];
    me: { rank: number; points: number; games?: number; wins?: number };
    min_players: number;
  };
  last_week: BattleAwardRow[];
  last_season: BattleAwardRow[];
}

/** K24 Lug'at 2.0 — daraja → mavzu → fleshkarta sessiyasi */
export interface VocabLevelCard {
  level: string;
  title_uz: string;
  title_ar: string;
  total: number;
  learned: number;
  topics: number;
}
export interface VocabLevels {
  levels: VocabLevelCard[];
  total: number;
  learned: number;
}
export interface VocabTopicCard {
  slug: string;
  title_uz: string;
  title_ar: string;
  icon: string;
  total: number;
  learned: number;
}
export interface VocabTopicList {
  level: string;
  title_uz: string;
  title_ar: string;
  total: number;
  learned: number;
  topics: VocabTopicCard[];
}
/** Fleshkarta so'zi (uz — asosiy ma'no; note_uz — eslatma/etimologiya) */
export interface VocabCard {
  key: string;
  ar: string;
  translit: string;
  uz: string;
  audio: string;
  example_ar: string;
  example_uz: string;
  note_uz: string;
  plural_ar: string;
  root: string;
  pos: string;
  topic: string;
}
export type VocabExamType = "ar_uz" | "audio_uz" | "uz_ar";
export interface VocabExamQ {
  key: string;
  type: VocabExamType;
  prompt: string;
  audio: string;
  options: string[];
  answer: string;
}
export interface VocabSessionData {
  level: string;
  topic: { slug: string; title_uz: string; title_ar: string; icon: string };
  mode: "new" | "review";
  batch: number;
  words: VocabCard[];
  exam: VocabExamQ[];
  remaining: number;
  total: number;
  learned: number;
}
export interface VocabSessionResult {
  correct: number;
  total: number;
  percent: number;
  passed: boolean;
  xp: number;
  xp_capped: boolean;
  added: number;
  wrong: (VocabCard & { type: VocabExamType; chosen: string })[];
  topic_total: number;
  topic_learned: number;
  remaining: number;
  new_badges: Badge[];
}

/** Lug'at imtihoni — daraja kesimida */
export interface VocabQuizItem {
  type: "ar_uz" | "uz_ar" | "audio_uz";
  word_id: string;
  ar: string;
  prompt: string;
  translit: string;
  audio: string;
  options: string[];
  answer: string;
  level: string;
  theme: string;
}

export interface VocabQuiz {
  level: string;
  theme: string;
  pass_score: number;
  total_words?: number;
  items: VocabQuizItem[];
}

export interface VocabQuizResult {
  score: number;
  passed: boolean;
  pass_score: number;
  xp_earned: number;
  added_to_review: number;
}

/** Daraja aniqlash testi (placement) */
export interface PlacementTier {
  done: false;
  tier: string;
  tier_title: string;
  tier_index: number;
  tier_count: number;
  pass_ratio: number;
  items: MicroTestItem[];
}

export interface PlacementDone {
  done: true;
  level: string;
  reason: string;
}

export type PlacementStep = PlacementTier | PlacementDone;

export interface PlacementResult {
  level: string;
  reason: string;
  start_lesson: string;
  saved: boolean;
}

/** Haftalik chellenj */
export interface ChallengeInfo {
  week: number;
  week_label: string;
  available: boolean;
  lessons_pool: number;
  questions: number;
  pass_score: number;
  xp_reward: number;
  attempted: boolean;
  passed: boolean;
  best_score: number | null;
}

export interface ChallengeData {
  attempt_id: number;
  week: number;
  week_label: string;
  items: MicroTestItem[];
  pass_score: number;
  xp_reward: number;
  lessons_pool: number;
}

export interface ChallengeResult {
  score: number;
  passed: boolean;
  correct: number;
  total: number;
  week: number;
  xp_earned: number;
  xp_already_claimed: boolean;
  srs_reset: number;
}

export interface AchievementsData {
  earned_count: number;
  total: number;
  badges: Badge[];
}

export interface RootSummary {
  root: string;
  meaning_uz: string;
  uz_cognates: string[];
  count: number;
  seen: boolean;
}

export interface DerivedWord {
  ar: string;
  uz: string;
  pattern: string;
  audio?: string;
  uz_cognate?: string;
}

export interface RootDetail {
  root: string;
  meaning_uz: string;
  uz_cognates: string[];
  audio?: string;
  derived: DerivedWord[];
}

/* ─────────────── Curriculum v2 (yangi dars playeri) ─────────────── */

export interface V2GrammarRow {
  ar: string;
  uz: string;
  form: string;
}

export interface V2Grammar {
  point_ar: string;
  explanation_uz: string;
  table: V2GrammarRow[];
  common_mistakes_uz: string[];
}

export interface V2RootEntry {
  root: string;
  meaning_uz: string;
  uz_cognates: string[];
  derived: { ar: string; uz: string; pattern: string }[];
}

export interface V2VocabItem {
  ar: string;
  translit: string;
  uz: string;
  root: string;
  pattern: string;
  pos: string;
  audio: string;
  example_ar: string;
  example_uz: string;
  srs: boolean;
}

export interface V2HejaziItem {
  msa_ar: string;
  hejazi_ar: string;
  translit: string;
  uz: string;
  audio: string;
}

export interface V2SkillQuestion {
  q_uz: string;
  a: string;
}

export interface V2Skills {
  reading: { text_ar: string; questions: V2SkillQuestion[] };
  listening: { audio: string; transcript_ar: string; questions: V2SkillQuestion[] };
  speaking: { task_uz: string; target_ar: string[]; eval: string };
  writing: { task_uz: string; eval: string };
}

export type MicroTestType =
  | "mcq"
  | "fill_blank"
  | "translate_uz_ar"
  | "translate_ar_uz"
  | "harakat"
  | "dictation"
  | "match_root"
  | "build_word"
  | "shadowing"
  | "order_words";

export interface MicroTestItem {
  type: MicroTestType;
  q_uz: string;
  q_ar: string;
  options: string[];
  answer: string;
  explain_uz: string;
  audio: string;
  root: string;
  pattern: string;
  words: string[];
}

/** A2+ darslardagi bosqichma-bosqich o'qish matni (content/reading/*.json). */
export interface ReadingPassage {
  stage: number;
  stages_total: number;
  level: string;
  lesson_id: string;
  title_uz: string;
  harakat: "full" | "partial" | "minimal";
  words: number;
  audio: string;
  text_ar: string;
  glossary: { ar: string; uz: string }[];
  questions: MicroTestItem[];
}

export interface LessonV2Data {
  id: string;
  level: string;
  module: string;
  order: number;
  title_uz: string;
  title_ar: string;
  can_do_uz: string;
  harakat_level: string;
  hook_uz: string;
  grammar: V2Grammar;
  roots: V2RootEntry[];
  vocabulary: V2VocabItem[];
  hejazi: V2HejaziItem[];
  skills: V2Skills;
  micro_test: MicroTestItem[];
  // Mikro-test urinishga qarab yig'iladi (qayta topshirishda boshqa savollar)
  test_attempt: number;
  pass_score: number;
  attempts_made: number;
  passage: ReadingPassage | null;
  srs_cards: { type: string; front: string; back: string; deck: string }[];
  meta: { title_uz: string; level: string; order: number; module: string };
}

export interface CompleteV2Response {
  xp_earned: number;
  perfect: boolean;
  score: number;
  passed: boolean;
  pass_score: number;
  first_time: boolean;
  srs_added: number;
  srs_reset: number;
  stats: Stats;
  new_badges: Badge[];
  checkpoint_available: boolean;
}

export interface CheckpointData {
  lesson_ids: string[];
  pass_percent: number;
  questions: MicroTestItem[];
}

export interface ProfileData {
  name: string;
  username: string;
  /** Taklif dasturi (K18.1): havola, ulashish, statistika */
  referral?: {
    link: string;
    share_url: string;
    invited: number;
    rewarded: number;
    days_earned: number;
    days_per_friend: number;
    max_rewards: number;
  };
  /** Speaking daftari hisoblari (K17.5) */
  speaking?: {
    mistakes: number;
    mock_attempts: number;
    mock_best: number;
    drill_attempts: number;
    drill_best: number;
  };
  level: string;
  target_level: string;
  target_date: string;
  daily_minutes: number;
  daily_xp_goal: number;
  goal: string;
  exams_passed: number;
  best_exam: number;
  cards_total: number;
  mistakes_now: number;
  stats: Stats;
  total_xp: number;
  longest_streak: number;
  member_since: string;
  achievements: AchievementsData;
}

/* ─────────────── Imtihon (K3) ─────────────── */

/** Bitta daraja imtihonining holati */
export interface ExamLevelState {
  level: string;
  available: boolean;
  already_passed: boolean;
  cooldown_until: string | null;
  minutes: number;
  counts: Record<string, number>;
  /** Ochiqmi: past darajalar doim ochiq, joriy — 80% dars, yuqori — yopiq */
  unlocked: boolean;
  /** "above" — reja darajasidan yuqori, "lessons" — darslar yetmadi */
  locked_reason: string;
  lessons_done: number;
  lessons_total: number;
  lessons_needed: number;
  percent: number;
}

export interface ExamInfo extends ExamLevelState {
  /** Foydalanuvchining reja darajasi */
  user_level: string;
  levels: ExamLevelState[];
  next_level: string | null;
}

/** Mini-imtihon (25% / 50% / 75%) */
export interface CheckpointItem {
  percent: number;
  need: number;
  unlocked: boolean;
  attempted: boolean;
  passed: boolean;
  best_score: number | null;
}

export interface CheckpointInfo {
  level: string;
  lessons_done: number;
  lessons_total: number;
  pass_score: number;
  checkpoints: CheckpointItem[];
  /** Hozir topshirish mumkin bo'lgan birinchi mini-imtihon foizi */
  due: number | null;
}

export interface CheckpointData {
  attempt_id: number;
  level: string;
  percent: number;
  lessons_covered: number;
  items: MicroTestItem[];
  pass_score: number;
}

export interface CheckpointResult {
  score: number;
  passed: boolean;
  correct: number;
  total: number;
  level: string;
  percent: number;
  xp_earned: number;
  srs_reset: number;
  locked: boolean;
}

export interface MyCertificate {
  cert_id: string;
  /** "level" — daraja imtihoni; "weekly" — haftalik reyting sovrini */
  kind: string;
  level: string;
  score: number;
  issued_at: string;
  png_url: string;
}

export interface ExamWriting {
  task_uz: string;
}

export interface ExamSpeaking {
  q_ar: string;
  audio: string;
}

/** A2 va yuqorida gapirish o'rniga: matn + tagidagi savollar */
export interface ExamPassage {
  id: string;
  title_uz: string;
  text_ar: string;
  questions: MicroTestItem[];
}

export interface ExamData {
  attempt_id: number;
  level: string;
  minutes: number;
  reading: MicroTestItem[];
  listening: MicroTestItem[];
  writing: ExamWriting[];
  speaking: ExamSpeaking[];
  passages: ExamPassage[];
}

export interface ExamResult {
  reading: number;
  listening: number;
  writing: number;
  /** 4-bo'lim bali — gapirish yoki matn o'qish (`fourth` ga qarab) */
  speaking: number;
  fourth: "speaking" | "passage";
  total: number;
  passed: boolean;
  timed_out: boolean;
  xp_earned: number;
  certificate: {
    cert_id: string;
    png_url: string;
    verify_code: string;
  } | null;
  /** Imtihondan o'tilgach ochilgan yangi daraja (yoki null) */
  promoted_to: string | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Init-Data": window.Telegram?.WebApp.initData ?? "",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    // Server tushuntirgan sababni ham olib chiqamiz (masalan ism validatsiyasi)
    let detail = "";
    try {
      detail = (await res.clone().json())?.detail ?? "";
    } catch {
      /* JSON emas — status kifoya */
    }
    const err = new Error(
      `API xatosi: ${res.status}${detail ? ` — ${detail}` : ""}`
    );
    (err as Error & { status: number; detail: string }).status = res.status;
    (err as Error & { status: number; detail: string }).detail = detail;
    throw err;
  }
  return res.json();
}

export const api = {
  getMe: () => request<MeResponse>("/api/me"),
  submitOnboarding: (payload: OnboardingPayload) =>
    request<{ ai_used: boolean; plan: PlanData }>("/api/onboarding", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getModules: () => request<LevelsResponse>("/api/modules"),
  getReview: (deck?: "msa" | "hejazi") =>
    request<{
      cards: ReviewCard[];
      total_due: number;
      msa_due: number;
      hejazi_due: number;
    }>(`/api/review${deck ? `?deck=${deck}` : ""}`),
  answerReview: (wordId: number, grade: ReviewGrade) =>
    request<{
      xp: number;
      interval_days: number;
      due_date: string;
      new_badges: Badge[];
    }>("/api/review/answer", {
      method: "POST",
      body: JSON.stringify({ word_id: wordId, grade }),
    }),
  getReferenceStats: () => request<ReferenceStats>("/api/reference/stats"),
  searchGrammar: (q: string, level = "") =>
    request<{ total: number; items: GrammarEntry[] }>(
      `/api/reference/grammar?q=${encodeURIComponent(q)}&level=${level}`
    ),
  searchVocab: (q: string, level = "", offset = 0) =>
    request<{ total: number; items: VocabEntry[] }>(
      `/api/reference/vocab?q=${encodeURIComponent(q)}&level=${level}&offset=${offset}`
    ),
  getVocabStats: () => request<VocabStats>("/api/vocab/stats"),
  /** K25 Oktagon */
  battleMe: () => request<BattleMe>("/api/battle/me"),
  battleTop: () =>
    request<{ items: BattleTopItem[]; me: { rank: number; points: number } }>("/api/battle/top"),
  battleHistory: () => request<{ items: BattleHistoryItem[] }>("/api/battle/history"),
  /** K25.3 — mavsum va haftalik Oktagon reytingi */
  battleSeason: () => request<BattleSeasonData>("/api/battle/season"),
  /** K24 Lug'at 2.0 */
  vocabLevels: () => request<VocabLevels>("/api/vocab/levels"),
  vocabTopics: (level: string) => request<VocabTopicList>(`/api/vocab/topics?level=${level}`),
  vocabSession: (level: string, topic: string) =>
    request<VocabSessionData>(`/api/vocab/session?level=${level}&topic=${encodeURIComponent(topic)}`),
  vocabFinish: (body: {
    level: string;
    topic: string;
    mode: "new" | "review" | "retry";
    answers: { key: string; type: VocabExamType; chosen: string }[];
    unknown: string[];
  }) =>
    request<VocabSessionResult>("/api/vocab/session/finish", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getVocabThemes: (level = "") =>
    request<{ items: VocabTheme[] }>(`/api/vocab/themes?level=${level}`),
  searchVocabBase: (q: string, level = "", theme = "", offset = 0) =>
    request<{ total: number; items: VocabWord[] }>(
      `/api/vocab/search?q=${encodeURIComponent(q)}&level=${level}` +
        `&theme=${encodeURIComponent(theme)}&offset=${offset}`
    ),
  getVocabDaily: (level = "", n = 20, theme = "") =>
    request<{ items: VocabWord[] }>(
      `/api/vocab/daily?level=${level}&n=${n}&theme=${encodeURIComponent(theme)}`
    ),
  learnVocab: (words: string[]) =>
    request<{ added: number }>("/api/vocab/learn", {
      method: "POST",
      body: JSON.stringify({ words }),
    }),
  getVocabQuiz: (level = "", theme = "", n = 20) =>
    request<VocabQuiz>(
      `/api/vocab/quiz?level=${level}&theme=${encodeURIComponent(theme)}&n=${n}`
    ),
  submitVocabQuiz: (payload: {
    level: string;
    correct: number;
    total: number;
    wrong_words: string[];
  }) =>
    request<VocabQuizResult>("/api/vocab/quiz/submit", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getLeaderboard: (period: LeaderPeriod = "week") =>
    request<LeaderboardData>(`/api/leaderboard?period=${period}`),
  getPlacementStep: (passed: string) =>
    request<PlacementStep>(`/api/placement/next?passed=${encodeURIComponent(passed)}`),
  finishPlacement: (results: Record<string, boolean>) =>
    request<PlacementResult>("/api/placement/finish", {
      method: "POST",
      body: JSON.stringify({ results }),
    }),
  getChallengeInfo: () => request<ChallengeInfo>("/api/challenge/info"),
  startChallenge: () =>
    request<ChallengeData>("/api/challenge/start", { method: "POST", body: "{}" }),
  submitChallenge: (payload: {
    attempt_id: number;
    correct: number;
    total: number;
    wrong_words: string[];
  }) =>
    request<ChallengeResult>("/api/challenge/submit", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getAchievements: () => request<AchievementsData>("/api/achievements"),
  getProfile: () => request<ProfileData>("/api/profile"),
  updateGoal: (dailyMinutes: number) =>
    request<{ daily_minutes: number; daily_xp_goal: number }>(
      "/api/settings/goal",
      { method: "POST", body: JSON.stringify({ daily_minutes: dailyMinutes }) }
    ),
  updateName: (name: string) =>
    request<{ name: string }>("/api/settings/name", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  getRoots: () =>
    request<{ roots: RootSummary[]; seen_count: number; total: number }>(
      "/api/roots"
    ),
  getRoot: (root: string) =>
    request<RootDetail>(`/api/roots/${encodeURIComponent(root)}`),
  addRootToSrs: (root: string) =>
    request<{ added: number }>("/api/roots/add-to-srs", {
      method: "POST",
      body: JSON.stringify({ root }),
    }),
  getLessonV2: (id: string) => request<LessonV2Data>(`/api/v2/lessons/${id}`),
  completeLessonV2: (
    id: string,
    correct: number,
    total: number,
    wrongWords: string[]
  ) =>
    request<CompleteV2Response>(`/api/v2/lessons/${id}/complete`, {
      method: "POST",
      body: JSON.stringify({ correct, total, wrong_words: wrongWords }),
    }),
  getCheckpoint: (lessonId: string) =>
    request<CheckpointData>(`/api/v2/checkpoint/${lessonId}`),
  completeCheckpoint: (
    lessonId: string,
    correct: number,
    total: number,
    wrongWords: string[]
  ) =>
    request<{
      score: number;
      passed: boolean;
      xp_earned: number;
      srs_reset: number;
    }>(`/api/v2/checkpoint/${lessonId}/complete`, {
      method: "POST",
      body: JSON.stringify({ correct, total, wrong_words: wrongWords }),
    }),
  evalWriting: (lessonId: string, text: string) =>
    request<{ ai: boolean; feedback_uz: string }>("/api/v2/eval/writing", {
      method: "POST",
      body: JSON.stringify({ lesson_id: lessonId, text }),
    }),
  getExamInfo: () => request<ExamInfo>("/api/exam/info"),
  getMyCertificates: () =>
    request<{ certificates: MyCertificate[] }>("/api/my-certificates"),
  startExam: (level = "") =>
    request<ExamData>(
      `/api/exam/start${level ? `?level=${encodeURIComponent(level)}` : ""}`,
      { method: "POST", body: "{}" }
    ),
  submitExam: (payload: {
    attempt_id: number;
    reading_correct: number;
    listening_correct: number;
    writing_score: number;
    speaking_score: number;
    passage_correct: number;
    holder_name: string;
  }) =>
    request<ExamResult>("/api/exam/submit", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getCheckpointInfo: () => request<CheckpointInfo>("/api/checkpoint/info"),
  startCheckpoint: (percent: number) =>
    request<CheckpointData>(`/api/checkpoint/start?percent=${percent}`, {
      method: "POST",
      body: "{}",
    }),
  submitCheckpoint: (payload: {
    attempt_id: number;
    correct: number;
    total: number;
    wrong_words: string[];
  }) =>
    request<CheckpointResult>("/api/checkpoint/submit", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getWeakPractice: () =>
    request<{ items: MicroTestItem[]; reason?: string }>("/api/practice/weak"),
  completeWeakPractice: (correct: number, total: number, wrongWords: string[]) =>
    request<{ xp_earned: number }>("/api/practice/weak/complete", {
      method: "POST",
      body: JSON.stringify({ correct, total, wrong_words: wrongWords }),
    }),
  resetPlan: () =>
    request<{ ok: boolean }>("/api/settings/reset-plan", {
      method: "POST",
      body: "{}",
    }),
  rateLesson: (lessonId: string, rating: 1 | -1) =>
    request<{ ok: boolean }>(`/api/v2/lessons/${lessonId}/rate`, {
      method: "POST",
      body: JSON.stringify({ rating }),
    }),
  submitFeedback: (text: string, context = "") =>
    request<{ ok: boolean }>("/api/feedback", {
      method: "POST",
      body: JSON.stringify({ text, context }),
    }),
  reportClientError: (message: string, context = "") =>
    request<{ ok: boolean }>("/api/client-error", {
      method: "POST",
      body: JSON.stringify({ message, context }),
    }).catch(() => {}),
  getRoleplayScenarios: () =>
    request<{ scenarios: RoleplayScenario[] }>("/api/v2/roleplay/scenarios"),
  roleplayReply: (
    scenarioId: string,
    history: { role: "user" | "assistant"; content: string }[]
  ) =>
    request<RoleplayReply>("/api/v2/roleplay/reply", {
      method: "POST",
      body: JSON.stringify({ scenario_id: scenarioId, history }),
    }),

  // ── AI ustoz (jonli suhbat) ──
  getTutorTopics: () => request<TutorTopics>("/api/v2/tutor/topics"),
  tutorTurn: (body: {
    session_key: string;
    topic_id: string;
    history: { role: "user" | "assistant"; content: string }[];
    voice: boolean;
    mode: "chat" | "mock";
    mock_id?: string;
  }) =>
    request<TutorTurnResponse>("/api/v2/tutor/turn", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  tutorTranscribe: (audio: Blob, filename: string, prompt: string, sessionKey = "", topicId = "") => {
    const fd = new FormData();
    fd.append("file", audio, filename);
    fd.append("prompt", prompt);
    // Mock: aniqlik bali serverda sessiya bo'yicha saqlanadi (talaffuz mezoni)
    if (sessionKey) fd.append("session_key", sessionKey);
    // Mavzu lug'ati Whisper prompt'iga — o'quvchi so'zlari tanish bo'ladi
    if (topicId) fd.append("topic_id", topicId);
    return upload<{ text: string; confidence: number }>("/api/v2/tutor/transcribe", fd);
  },
  tutorPronounce: (
    audio: Blob,
    filename: string,
    target: string,
    drill?: { key: string; idx: number }
  ) => {
    const fd = new FormData();
    fd.append("file", audio, filename);
    fd.append("target", target);
    if (drill) {
      fd.append("drill_key", drill.key);
      fd.append("idx", String(drill.idx));
    }
    return upload<TutorPronounceResult>("/api/v2/tutor/pronounce", fd);
  },
  tutorDrill: (topic_id: string) =>
    request<DrillStart>(`/api/v2/tutor/drill?topic_id=${encodeURIComponent(topic_id)}`),
  tutorDrillFinish: (key: string) =>
    request<DrillFinish>("/api/v2/tutor/drill/finish", {
      method: "POST",
      body: JSON.stringify({ key }),
    }),
  getDaily: () => request<DailyInfo>("/api/v2/tutor/daily"),
  answerDaily: (text: string, voice: boolean) =>
    request<{ result: DailyResult; streak: number; best: number; xp: number; new_badges?: Badge[] }>(
      "/api/v2/tutor/daily/answer",
      { method: "POST", body: JSON.stringify({ text, voice }) }
    ),
  tutorListen: (topic_id: string, kind: "choice" | "dictation") =>
    request<ListenStart>(
      `/api/v2/tutor/listen?topic_id=${encodeURIComponent(topic_id)}&kind=${kind}`
    ),
  tutorListenAnswer: (body: { key: string; idx: number; choice?: number; text?: string }) =>
    request<ListenAnswer>("/api/v2/tutor/listen/answer", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  tutorListenFinish: (key: string) =>
    request<ListenFinish>("/api/v2/tutor/listen/finish", {
      method: "POST",
      body: JSON.stringify({ key }),
    }),
  tutorSay: (text: string) =>
    request<{ audio_url: string }>("/api/v2/tutor/say", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  getTutorLog: () => request<TutorLog>("/api/v2/tutor/log"),
  tutorRate: (body: {
    session_key: string;
    mode: "chat" | "mock" | "daily" | "drill" | "listen";
    topic: string;
    good: boolean;
    comment: string;
  }) =>
    request<{ ok: boolean }>("/api/v2/tutor/rate", { method: "POST", body: JSON.stringify(body) }),
  deleteMistake: (id: number) =>
    request<{ ok: boolean }>(`/api/v2/tutor/mistakes/${id}`, { method: "DELETE" }),
  tutorFinish: (session_key: string) =>
    request<TutorFinishResult>("/api/v2/tutor/finish", {
      method: "POST",
      body: JSON.stringify({ session_key }),
    }),
  tutorSaveWord: (ar: string, uz: string) =>
    request<{ added: number }>("/api/v2/tutor/save_word", {
      method: "POST",
      body: JSON.stringify({ ar, uz }),
    }),

  // ── VIP tarif / to'lov ──
  getPayInfo: () => request<PayInfo>("/api/pay/info"),
  startTrial: () =>
    request<{ ok: boolean; days: number; vip_until: string | null }>("/api/pay/trial", {
      method: "POST",
    }),
  submitReceipt: (file: File, plan: string) => {
    const fd = new FormData();
    fd.append("file", file, file.name);
    fd.append("plan", plan);
    return upload<{ ok: boolean; request_id: number; status: string }>(
      "/api/pay/receipt",
      fd
    );
  },
  // ── Yozuv mashqi (K19.2) ──
  getWriting: () => request<WritingInfo>("/api/v2/tutor/writing"),
  /** #F70: yozma mashqda rad etilgan javob — admin /javoblar uchun (jimgina, xato bo'lsa e'tiborsiz) */
  logWrongAnswer: (body: { context: string; ex_type: string; q: string; expected: string; given: string }) =>
    request<{ ok: boolean }>("/api/v2/answer-log", { method: "POST", body: JSON.stringify(body) }).catch(() => ({ ok: false })),
  /** K22.4: so'nggi kunlarda o'rganilgan so'zlar (kunlar bo'yicha) */
  recentWords: (days = 7) => request<{ days: RecentWordsDay[]; total: number }>(`/api/words/recent?days=${days}`),
  /** K21.5: haftalik natija kartasi (send=true — botga ham yuboriladi) */
  shareWeek: (send: boolean) =>
    request<ShareCardInfo>("/api/share/week", { method: "POST", body: JSON.stringify({ send }) }),
  /** K21.6: harf chizish */
  getTrace: () => request<TraceInfo>("/api/v2/trace"),
  finishTrace: (scores: Record<string, number>) =>
    request<TraceFinish>("/api/v2/trace/finish", { method: "POST", body: JSON.stringify({ scores }) }),
  checkWriting: (blob: Blob, filename: string) => {
    const fd = new FormData();
    fd.append("file", blob, filename);
    return upload<WritingCheck>("/api/v2/tutor/writing/check", fd);
  },
};

export interface PayPlan {
  id: string;
  title: string;
  days: number;
  months: number;
  price: number;
  /** Chegirma faol bo'lsa ustidan chiziladigan eski narx, aks holda 0 */
  old_price: number;
  /** Shu tarif uchun chegirma foizi (eski → yangi narxdan hisoblangan) */
  discount_percent: number;
  per_day: number;
  per_month: number;
}

export interface PayInfo {
  /** Bir martalik VIP sinov (K18.1) */
  trial_available: boolean;
  trial_days: number;
  referral_days: number;
  /** K23.4: VIP'da kuchliroq AI model (qisqa nomi), bo'sh = yo'q */
  vip_model?: string;
  vip: boolean;
  vip_until: string | null;
  vip_days_left: number;
  /** Chek yuborilgan, admin hali tekshirmagan */
  pending: boolean;
  card_number: string;
  card_holder: string;
  support_username: string;
  discount: {
    enabled: boolean;
    active: boolean;
    percent: number;
    until: string | null;
    hours: number;
  };
  plans: PayPlan[];
  proof: { learners: number; lessons_done: number; like_percent: number; ratings: number };
  testimonials: { name: string; text: string; level?: string }[];
}

/** Multipart yuklash — Content-Type'ni brauzer o'zi (boundary bilan) qo'yadi */
async function upload<T>(path: string, body: FormData): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    body,
    headers: { "X-Init-Data": window.Telegram?.WebApp.initData ?? "" },
  });
  if (!res.ok) {
    let detail = "";
    try {
      detail = (await res.clone().json())?.detail ?? "";
    } catch {
      /* JSON emas */
    }
    const err = new Error(`API xatosi: ${res.status}${detail ? ` — ${detail}` : ""}`);
    (err as Error & { status: number; detail: string }).status = res.status;
    (err as Error & { status: number; detail: string }).detail = detail;
    throw err;
  }
  return res.json();
}

export interface TutorTopic {
  id: string;
  emoji: string;
  title_uz: string;
  desc_uz: string;
  min_level: string;
  /** O'quvchi darajasiga mos (aks holda "B1+" yorlig'i bilan ko'rsatiladi) */
  recommended: boolean;
}

export interface TutorMock {
  id: string;
  emoji: string;
  title_uz: string;
  desc_uz: string;
  min_level: string;
  questions: number;
  recommended: boolean;
}

export interface TutorTopics {
  level: string;
  topics: TutorTopic[];
  mocks: TutorMock[];
  mock_results: { mock_id: string; score: number; date: string }[];
  vip: boolean;
  vip_days_left: number;
  /** VIP'siz kunlik bepul javoblar */
  free_turns: number;
  /** VIP kunlik javoblar limiti (yorliq uchun) */
  vip_turns: number;
  /** K23.4: VIP suhbat/mock kuchliroq modelda — qisqa nomi («Sonnet 5»), bo'sh = farq yo'q */
  vip_model?: string;
  /** Bir martalik VIP sinov (K18.1) */
  trial_available?: boolean;
  trial_days?: number;
  price: { month: number; per_day: number };
  turns_left: number;
  daily_limit: number;
  /** Anthropic kaliti sozlangan — AI ishlaydi */
  ai: boolean;
  /** STT kaliti sozlangan — mikrofon ishlaydi */
  voice: boolean;
}

export interface TutorNewWord {
  ar: string;
  translit: string;
  uz: string;
}

export interface TutorReply {
  ar: string;
  translit: string;
  uz: string;
  correction_ok: boolean;
  fixed_ar: string;
  note_uz: string;
  hint_uz: string;
  new_words: TutorNewWord[];
  /** O'quvchi savol bersa — o'zbekcha tushuntirish */
  answer_uz: string;
  /** K22.3: «qanday aytaman?» / o'zbekcha javob — aytish kerak bo'lgan arabcha jumla */
  say_ar?: string;
  say_translit?: string;
  done: boolean;
  // Mock imtihon rejimi (mode: "mock")
  score?: number;
  feedback_uz?: string;
  ideal_ar?: string;
  /** Mock mezonlari (K17.6) */
  vocab?: number;
  grammar?: number;
  content?: number;
  pron?: number;
}

export interface TutorTurnResponse {
  reply: TutorReply;
  /** edge-tts mp3 (bo'sh bo'lsa brauzer TTS'ga tushamiz) */
  audio_url: string;
  turns_left: number;
  vip: boolean;
  usage: { in?: number; out?: number; cache_read?: number; cache_write?: number };
}

/** Mock javobi mezonlari: -1 = o'lchanmagan (talaffuz faqat ovozli javobda) */
export interface MockCriteria {
  vocab: number;
  grammar: number;
  content: number;
  pron: number;
}

export interface TutorPronounceResult {
  transcript: string;
  score: number;
  words: ScoredWord[];
}

/** So'zma-so'z baho: ok — aynan eshitildi; close — Whisper imlosi farq qildi
 *  (عملك→عملوك, الحلوى→الحلوة) — sariq, ball 70% hisoblanadi; ikkalasi ham yo'q — qizil. */
export interface ScoredWord {
  ar: string;
  ok: boolean;
  close?: boolean;
}

export function wordClass(w: ScoredWord): string {
  if (w.ok) return "";
  return w.close ? "text-gold underline decoration-2" : "text-terracotta underline decoration-2";
}

// ── Talaffuz mashqi (LLM'siz, bepul) ──
export interface DrillItem {
  idx: number;
  ar: string;
  translit: string;
  uz: string;
  word: { ar: string; translit: string; uz: string };
  audio_url: string;
}

export interface DrillStart {
  key: string;
  level: string;
  topic_id: string;
  items: DrillItem[];
  voice: boolean;
}

export interface DrillFinish {
  topic_id: string;
  score: number;
  count: number;
  total: number;
  new_badges?: Badge[];
  xp: number;
  /** har jumla uchun eng yaxshi ball, -1 = aytilmagan */
  scores: number[];
  items: { ar: string; uz: string }[];
}

// ── Tinglab tushunish (LLM'siz, bepul) ──
export interface ListenStart {
  key: string;
  kind: "choice" | "dictation";
  level: string;
  topic_id: string;
  /** Matn oldindan berilmaydi — faqat audio va (tanlash rejimida) variantlar */
  items: { idx: number; audio_url: string; options?: string[] }[];
}

export interface ListenAnswer {
  correct: boolean;
  score: number;
  /** tanlash: to'g'ri variant indeksi */
  answer?: number;
  /** diktant: so'zma-so'z belgilar */
  words?: ScoredWord[];
  ar: string;
  translit: string;
  uz: string;
  word: { ar: string; translit: string; uz: string };
}

export interface ListenFinish {
  topic_id: string;
  kind: string;
  score: number;
  count: number;
  new_badges?: Badge[];
  total: number;
  xp: number;
  scores: number[];
  items: { ar: string; translit: string; uz: string }[];
}

// ── Speaking daftari ──
export interface TutorMistakeItem {
  id: number;
  kind: "chat" | "mock";
  topic: string;
  title: string;
  said_ar: string;
  fixed_ar: string;
  note_uz: string;
  date: string;
}

export interface SpeakingHistoryItem {
  title: string;
  emoji: string;
  best: number;
  last: number;
  attempts: number;
  history: number[];
  date: string;
}

export interface TutorLog {
  mistakes: TutorMistakeItem[];
  mocks: (SpeakingHistoryItem & { mock_id: string })[];
  drills: (SpeakingHistoryItem & { topic_id: string })[];
  listens?: (SpeakingHistoryItem & { topic_id: string; kind: string })[];
}

export interface TutorFinishResult {
  turns: number;
  ok_turns: number;
  voice_turns: number;
  xp: number;
  new_badges?: Badge[];
  /** Mock imtihon: o'rtacha ball va har savol bali */
  mock?: boolean;
  score?: number;
  scores?: number[];
  mock_id?: string;
  /** Mock: mezonlar o'rtachasi va (shaxsiy rekordda) sertifikat */
  criteria?: MockCriteria;
  certificate?: { cert_id: string; png_url: string; verify_code: string } | null;
}

export interface RoleplayScenario {
  id: string;
  title_uz: string;
  emoji: string;
  desc_uz: string;
}

export interface RoleplayReply {
  ar: string;
  uz: string;
  ai: boolean;
  done: boolean;
}
