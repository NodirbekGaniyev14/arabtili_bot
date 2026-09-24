import { useEffect, useState } from "react";
import ArabicBg from "./components/ArabicBg";
import NavBar, { type Tab } from "./components/NavBar";
import { initTheme } from "./lib/theme";
import { api, type MeResponse, type PlanData, type Stats } from "./lib/api";
import Home from "./pages/Home";
import Lessons from "./pages/Lessons";
import Onboarding from "./pages/onboarding/Onboarding";
import Profile from "./pages/Profile";
import Rating from "./pages/Rating";
import Review from "./pages/Review";
import RootLab from "./pages/RootLab";
import Exam from "./pages/Exam";
import Checkpoint from "./pages/Checkpoint";
import Challenge from "./pages/Challenge";
import Placement from "./pages/Placement";
import WeakPractice from "./pages/WeakPractice";
import RolePlay from "./pages/RolePlay";
import Tutor from "./pages/Tutor";
import Paywall from "./pages/Paywall";
import Reference from "./pages/Reference";
import SpeakingLog from "./pages/SpeakingLog";
import Writing from "./pages/Writing";
import Trace from "./pages/Trace";
import Battle from "./pages/Battle";
import TodayWords from "./pages/TodayWords";
import DailyTask from "./pages/DailyTask";
import Vocab from "./pages/Vocab";
import LessonPlayerV2 from "./pages/v2/LessonPlayerV2";

type Phase = "boot" | "onboarding" | "app" | "offline";

const EMPTY_STATS: Stats = {
  streak: 0,
  streak_freezes: 0,
  xp_today: 0,
  words: 0,
  lessons: 0,
  accuracy: 0,
  due_count: 0,
  next_lesson: null,
};

export default function App() {
  const [phase, setPhase] = useState<Phase>("boot");
  // Bot e'lonidagi tugma (#rating) — to'g'ri reytingga
  const [tab, setTab] = useState<Tab>(() => (window.location.hash === "#rating" ? "rating" : "home"));
  const [tgName, setTgName] = useState("");
  const [me, setMe] = useState<MeResponse | null>(null);
  const [activeLessonV2, setActiveLessonV2] = useState<string | null>(() => {
    // Dev/deep-link kirish: #lesson=a0-22
    const m = window.location.hash.match(/#lesson=([a-b]\d-\d{2})/);
    return m ? m[1] : null;
  });
  const [showRootLab, setShowRootLab] = useState(false);
  const [showExam, setShowExam] = useState(false);
  const [checkpointPct, setCheckpointPct] = useState<number | null>(null);
  const [showChallenge, setShowChallenge] = useState(false);
  const [showPlacement, setShowPlacement] = useState(false);
  const [showWeak, setShowWeak] = useState(false);
  const [showRolePlay, setShowRolePlay] = useState(false);
  // Bot xabaridagi tugma (#tutor) — to'g'ri AI ustozga
  const [showTutor, setShowTutor] = useState(() => window.location.hash === "#tutor");
  // Tanishuv kartasi (K20.4): ustoz shu mavzuda darhol boshlaydi
  const [tutorTopic, setTutorTopic] = useState("");
  // Home «Talaffuz mashqi» (K22.5) → ustozning drill bo'limi
  const [tutorTab, setTutorTab] = useState<"chat" | "drill" | undefined>(undefined);
  // Bot eslatmasidagi tugma (#vip) — ilova to'g'ridan-to'g'ri VIP sahifasida ochiladi
  const [showPaywall, setShowPaywall] = useState(() => window.location.hash === "#vip");
  const [showReference, setShowReference] = useState(false);
  const [showSpeaking, setShowSpeaking] = useState<"mistakes" | "results" | null>(null);
  // Bot eslatmasidagi tugma (#daily) — to'g'ri kunlik savolga
  const [showDaily, setShowDaily] = useState(() => window.location.hash === "#daily");
  // Bot eslatmasidagi tugma (#writing) — yozuv mashqiga (K19.2)
  const [showWriting, setShowWriting] = useState(() => window.location.hash === "#writing");
  // Harf chizish mashqi (K21.6) — #trace
  const [showTrace, setShowTrace] = useState(() => window.location.hash === "#trace");
  // Oktagon — 1v1 lug'at jangi (K25) — #battle
  const [showBattle, setShowBattle] = useState(() => window.location.hash === "#battle");
  // «Yangi so'zlarim» (K22.4) — #words
  const [showWords, setShowWords] = useState(() => window.location.hash === "#words");

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    tg?.ready();
    tg?.expand();
    initTheme(); // yorug'/qorong'i — Telegram mavzusi yoki profil tanlovi (lib/theme.ts)
    if (tg?.initDataUnsafe.user) {
      setTgName(tg.initDataUnsafe.user.first_name);
    }

    loadMe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Server javob bermasa ONBOARDINGGA TASHLAMAYMIZ.
   *
   * Ilgari `.catch(() => setPhase("onboarding"))` edi: server bir soniya
   * yiqilsa ham foydalanuvchi «Salom! Men Jamalman» ekranini ko'rib,
   * hamma natijam o'chibdi deb o'ylardi va qaytadan test topshirardi.
   * Endi xato bo'lsa — qayta urinish ekrani, ma'lumot joyida qoladi. */
  const loadMe = () => {
    setPhase("boot");
    api
      .getMe()
      .then((m) => {
        setMe(m);
        setPhase(m.has_plan ? "app" : "onboarding");
      })
      .catch(() => setPhase("offline"));
  };

  const handleOnboardingDone = (plan: PlanData, newName: string) => {
    setMe((m) => ({
      name: newName || tgName,
      has_plan: true,
      plan,
      stats: m?.stats ?? EMPTY_STATS,
      vip: m?.vip ?? false,
      vip_days_left: m?.vip_days_left ?? 0,
      vip_price: m?.vip_price ?? { month: 0, per_day: 0 },
    }));
    setTab("home");
    setPhase("app");
    // K22.1: «Birinchi darsni boshlash» — Home emas, darhol dars (voronka: 69% birinchi darsni ochmasdi)
    setActiveLessonV2(plan.start_lesson || "a0-01");
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
          <span className="font-arabic text-4xl text-white leading-none pt-1">
            ع
          </span>
        </div>
        <span className="font-extrabold text-ink-soft">Arabiy</span>
      </div>
    );
  }

  if (phase === "offline") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 px-8 text-center">
        <div className="text-5xl">📡</div>
        <h1 className="text-xl font-extrabold">Serverga ulanib bo'lmadi</h1>
        <p className="text-sm text-ink-soft font-semibold">
          Ma'lumotlaringiz joyida — hech narsa yo'qolmadi. Internetni tekshirib,
          qayta urinib ko'ring.
        </p>
        <button
          onClick={loadMe}
          className="w-full max-w-xs rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg"
        >
          Qayta urinish
        </button>
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

  // Daraja testi MAJBURIY EMAS. Ilgari eski foydalanuvchilarga ilova
  // ochilganda majburiy qayta test chiqardi — bu «progressim o'chibdi»
  // taassurotini berardi. Endi u faqat Profil sahifasidan ixtiyoriy
  // (showPlacement) ochiladi.
  if (showPlacement) {
    return (
      <div className="min-h-screen">
        <ArabicBg />
        <Placement
          onDone={() => {
            setShowPlacement(false);
            api.getMe().then(setMe).catch(() => {});
          }}
          onClose={() => setShowPlacement(false)}
        />
      </div>
    );
  }

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
            onOpenChallenge={() => setShowChallenge(true)}
            onOpenWeak={() => setShowWeak(true)}
            onOpenRolePlay={() => setShowRolePlay(true)}
            onOpenTutor={(topicId?: string) => {
              setTutorTopic(topicId ?? "");
              setShowTutor(true);
            }}
            introPending={!!me?.intro_pending}
            introTopic={me?.intro_topic ?? "tanishish"}
            vip={me?.vip ?? false}
            daily={me?.daily}
            onOpenDaily={() => setShowDaily(true)}
            writing={me?.writing}
            onOpenWriting={() => setShowWriting(true)}
            onOpenTrace={() => setShowTrace(true)}
            onOpenBattle={() => setShowBattle(true)}
            onOpenReference={() => setShowReference(true)}
            onOpenVocab={() => setTab("vocab")}
            onOpenWords={() => setShowWords(true)}
            onOpenDrill={() => {
              setTutorTab("drill");
              setShowTutor(true);
            }}
            onGoLessons={() => setTab("lessons")}
          />
        )}
        {tab === "lessons" && (
          <Lessons
            key={stats.lessons}
            onOpen={setActiveLessonV2}
            onOpenCheckpoint={setCheckpointPct}
          />
        )}
        {tab === "vocab" && <Vocab />}
        {tab === "review" && <Review onDone={refreshMe} />}
        {tab === "rating" && <Rating />}
        {tab === "profile" && (
          <Profile
            onOpenPlacement={() => setShowPlacement(true)}
            onOpenPaywall={() => setShowPaywall(true)}
            vip={me?.vip ?? false}
            vipDaysLeft={me?.vip_days_left ?? 0}
            vipPrice={me?.vip_price}
            onProfileChange={refreshMe}
            onOpenSpeaking={setShowSpeaking}
          />
        )}
      </main>

      <NavBar tab={tab} onChange={setTab} reviewBadge={stats.due_count} />

      {showRootLab && <RootLab onClose={() => setShowRootLab(false)} />}

      {showRolePlay && <RolePlay onClose={() => setShowRolePlay(false)} />}

      {showTutor && (
        <Tutor
          initialTopicId={tutorTopic || undefined}
          initialTab={tutorTab}
          onClose={() => {
            setShowTutor(false);
            setTutorTopic("");
            setTutorTab(undefined);
            // Suhbat XP'si va yangi SRS kartalari statistikaga tushsin
            api.getMe().then(setMe).catch(() => {});
          }}
        />
      )}

      {showPaywall && (
        <Paywall
          onClose={() => {
            setShowPaywall(false);
            api.getMe().then(setMe).catch(() => {});
          }}
        />
      )}

      {showReference && <Reference onClose={() => setShowReference(false)} />}

      {showSpeaking && (
        <SpeakingLog initialTab={showSpeaking} onClose={() => setShowSpeaking(null)} />
      )}

      {showBattle && (
        <Battle
          onClose={() => {
            setShowBattle(false);
            api.getMe().then(setMe).catch(() => {});
          }}
        />
      )}

      {showTrace && (
        <Trace
          onClose={() => {
            setShowTrace(false);
            api.getMe().then(setMe).catch(() => {});
          }}
          onDone={() => api.getMe().then(setMe).catch(() => {})}
        />
      )}

      {showWords && (
        <TodayWords
          goal={me?.stats?.today?.new_words_goal ?? 5}
          onClose={() => setShowWords(false)}
          onOpenVocab={() => {
            setShowWords(false);
            setTab("vocab");
          }}
          onGoReview={() => {
            setShowWords(false);
            setTab("review");
          }}
        />
      )}

      {showWriting && (
        <Writing
          onClose={() => {
            setShowWriting(false);
            api.getMe().then(setMe).catch(() => {});
          }}
          onDone={() => api.getMe().then(setMe).catch(() => {})}
        />
      )}

      {showDaily && (
        <DailyTask
          onClose={() => {
            setShowDaily(false);
            api.getMe().then(setMe).catch(() => {});
          }}
          onDone={() => api.getMe().then(setMe).catch(() => {})}
        />
      )}

      {showExam && (
        <Exam
          onClose={() => {
            setShowExam(false);
            api.getMe().then(setMe).catch(() => {});
          }}
        />
      )}

      {showChallenge && (
        <Challenge
          onClose={() => {
            setShowChallenge(false);
            api.getMe().then(setMe).catch(() => {});
          }}
        />
      )}

      {checkpointPct !== null && (
        <Checkpoint
          percent={checkpointPct}
          onClose={() => {
            setCheckpointPct(null);
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
          key={activeLessonV2}
          lessonId={activeLessonV2}
          onNext={(id, stats) => {
            setMe((m) => (m ? { ...m, stats } : m));
            setActiveLessonV2(id);
          }}
          onClose={() => {
            setActiveLessonV2(null);
            // Keyingi dars, modul qulflari va statistikani yangilaymiz
            api.getMe().then(setMe).catch(() => {});
          }}
          onFinish={(stats) => {
            // Statistika yangilanadi VA pleyer yopiladi — aks holda
            // "Davom etish" tugmasi hech narsa qilmayotgandek ko'rinadi
            setMe((m) => (m ? { ...m, stats } : m));
            setActiveLessonV2(null);
          }}
        />
      )}
    </div>
  );
}
