import { useEffect, useState } from "react";
import ArabicBg from "./components/ArabicBg";
import NavBar, { type Tab } from "./components/NavBar";
import { api, type MeResponse, type PlanData, type Stats } from "./lib/api";
import Home from "./pages/Home";
import Lessons from "./pages/Lessons";
import Onboarding from "./pages/onboarding/Onboarding";
import Profile from "./pages/Profile";
import Rating from "./pages/Rating";
import Review from "./pages/Review";
import RootLab from "./pages/RootLab";
import Exam from "./pages/Exam";
import WeakPractice from "./pages/WeakPractice";
import LessonPlayerV2 from "./pages/v2/LessonPlayerV2";

type Phase = "boot" | "onboarding" | "app";

const EMPTY_STATS: Stats = {
  streak: 0,
  xp_today: 0,
  words: 0,
  lessons: 0,
  accuracy: 0,
  due_count: 0,
  next_lesson: null,
};

export default function App() {
  const [phase, setPhase] = useState<Phase>("boot");
  const [tab, setTab] = useState<Tab>("home");
  const [tgName, setTgName] = useState("");
  const [me, setMe] = useState<MeResponse | null>(null);
  const [activeLessonV2, setActiveLessonV2] = useState<string | null>(() => {
    // Dev/deep-link kirish: #lesson=a0-22
    const m = window.location.hash.match(/#lesson=([a-b]\d-\d{2})/);
    return m ? m[1] : null;
  });
  const [showRootLab, setShowRootLab] = useState(false);
  const [showExam, setShowExam] = useState(false);
  const [showWeak, setShowWeak] = useState(false);

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    tg?.ready();
    tg?.expand();
    tg?.setHeaderColor?.("#FAF6EE");
    tg?.setBackgroundColor?.("#FAF6EE");
    if (tg?.initDataUnsafe.user) {
      setTgName(tg.initDataUnsafe.user.first_name);
    }

    api
      .getMe()
      .then((m) => {
        setMe(m);
        setPhase(m.has_plan ? "app" : "onboarding");
      })
      .catch(() => setPhase("onboarding"));
  }, []);

  const handleOnboardingDone = (plan: PlanData, newName: string) => {
    setMe((m) => ({
      name: newName || tgName,
      has_plan: true,
      plan,
      stats: m?.stats ?? EMPTY_STATS,
    }));
    setTab("home");
    setPhase("app");
    // Statistika va keyingi darsni serverdan olamiz
    api.getMe().then(setMe).catch(() => {});
  };

  const refreshMe = () => {
    api.getMe().then(setMe).catch(() => {});
    setTab("home");
  };

  if (phase === "boot") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3">
        <div className="w-16 h-16 rounded-2xl bg-emerald-deep flex items-center justify-center animate-pulse">
          <span className="font-arabic text-4xl text-sand leading-none pt-1">
            ع
          </span>
        </div>
        <span className="font-extrabold text-ink-soft">Arabiy</span>
      </div>
    );
  }

  if (phase === "onboarding") {
    return (
      <div className="min-h-screen">
        <ArabicBg />
        <Onboarding initialName={tgName} onDone={handleOnboardingDone} />
      </div>
    );
  }

  const displayName = me?.name || tgName;
  const stats = me?.stats ?? EMPTY_STATS;

  return (
    <div className="min-h-screen">
      <ArabicBg />

      <main className="relative z-10 pb-24 max-w-md mx-auto">
        {tab === "home" && (
          <Home
            name={displayName}
            xpGoal={me?.plan?.daily_xp_goal ?? 30}
            stats={stats}
            onStartLesson={setActiveLessonV2}
            onGoReview={() => setTab("review")}
            onOpenRootLab={() => setShowRootLab(true)}
            onOpenExam={() => setShowExam(true)}
            onOpenWeak={() => setShowWeak(true)}
            onGoLessons={() => setTab("lessons")}
          />
        )}
        {tab === "lessons" && (
          <Lessons key={stats.lessons} onOpen={setActiveLessonV2} />
        )}
        {tab === "review" && <Review onDone={refreshMe} />}
        {tab === "rating" && <Rating />}
        {tab === "profile" && <Profile />}
      </main>

      <NavBar tab={tab} onChange={setTab} reviewBadge={stats.due_count} />

      {showRootLab && <RootLab onClose={() => setShowRootLab(false)} />}

      {showExam && (
        <Exam
          onClose={() => {
            setShowExam(false);
            api.getMe().then(setMe).catch(() => {});
          }}
        />
      )}

      {showWeak && (
        <WeakPractice
          onClose={() => {
            setShowWeak(false);
            api.getMe().then(setMe).catch(() => {});
          }}
        />
      )}

      {activeLessonV2 && (
        <LessonPlayerV2
          lessonId={activeLessonV2}
          onClose={() => {
            setActiveLessonV2(null);
            // Keyingi dars, modul qulflari va statistikani yangilaymiz
            api.getMe().then(setMe).catch(() => {});
          }}
          onFinish={(stats) => {
            setMe((m) => (m ? { ...m, stats } : m));
          }}
        />
      )}
    </div>
  );
}
