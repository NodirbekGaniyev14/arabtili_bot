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
  xp_today: number;
  words: number;
  lessons: number;
  accuracy: number;
  due_count: number;
  next_lesson: NextLesson | null;
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
  is_me: boolean;
  is_demo: boolean;
}

export interface LeaderboardData {
  league: League;
  all_leagues: League[];
  my_rank: number;
  my_weekly_xp: number;
  entries: LeaderboardEntry[];
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
  srs_cards: { type: string; front: string; back: string; deck: string }[];
  meta: { title_uz: string; level: string; order: number; module: string };
}

export interface CompleteV2Response {
  xp_earned: number;
  perfect: boolean;
  score: number;
  passed: boolean;
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

export interface ExamInfo {
  level: string;
  available: boolean;
  already_passed: boolean;
  cooldown_until: string | null;
  minutes: number;
  counts: Record<string, number>;
  /** Darslar qulfi — daraja darslarining 80% tugagach ochiladi */
  unlocked: boolean;
  lessons_done: number;
  lessons_total: number;
  lessons_needed: number;
  next_level: string | null;
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

export interface ExamData {
  attempt_id: number;
  level: string;
  minutes: number;
  reading: MicroTestItem[];
  listening: MicroTestItem[];
  writing: ExamWriting[];
  speaking: ExamSpeaking[];
}

export interface ExamResult {
  reading: number;
  listening: number;
  writing: number;
  speaking: number;
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
  if (!res.ok) throw new Error(`API xatosi: ${res.status}`);
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
  getLeaderboard: () => request<LeaderboardData>("/api/leaderboard"),
  getAchievements: () => request<AchievementsData>("/api/achievements"),
  getProfile: () => request<ProfileData>("/api/profile"),
  updateGoal: (dailyMinutes: number) =>
    request<{ daily_minutes: number; daily_xp_goal: number }>(
      "/api/settings/goal",
      { method: "POST", body: JSON.stringify({ daily_minutes: dailyMinutes }) }
    ),
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
  startExam: () => request<ExamData>("/api/exam/start", { method: "POST", body: "{}" }),
  submitExam: (payload: {
    attempt_id: number;
    reading_correct: number;
    listening_correct: number;
    writing_score: number;
    speaking_score: number;
    holder_name: string;
  }) =>
    request<ExamResult>("/api/exam/submit", {
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
};

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
