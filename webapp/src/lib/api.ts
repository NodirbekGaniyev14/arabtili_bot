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
  lessons: LessonMeta[];
}

export interface ComingSoonModule {
  id: string;
  title: string;
  available: false;
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

export interface ProfileData {
  name: string;
  username: string;
  level: string;
  target_level: string;
  target_date: string;
  daily_minutes: number;
  daily_xp_goal: number;
  stats: Stats;
  total_xp: number;
  longest_streak: number;
  member_since: string;
  achievements: AchievementsData;
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
  getModules: () =>
    request<{ modules: ModuleInfo[]; coming_soon: ComingSoonModule[] }>(
      "/api/modules"
    ),
  getLesson: (id: string) => request<LessonData>(`/api/lessons/${id}`),
  completeLesson: (id: string, correct: number, total: number) =>
    request<CompleteResponse>(`/api/lessons/${id}/complete`, {
      method: "POST",
      body: JSON.stringify({ correct, total }),
    }),
  getReview: () =>
    request<{ cards: ReviewCard[]; total_due: number }>("/api/review"),
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
};
